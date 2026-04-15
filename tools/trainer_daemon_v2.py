"""Remote training worker — matches prod's ``/api/training/jobs/*`` protocol.

This is the v2 daemon that pairs with the *current* production endpoints at
https://binmuhayyaai.com:

    GET  /api/training/jobs/next-queued            → peek
    POST /api/training/jobs/{job_id}/claim         → claim (atomic)
    POST /api/training/jobs/{job_id}/artifact      → upload + complete

There is no heartbeat or fail endpoint in prod's current implementation, so
this daemon just peeks → claims → trains → uploads. On uncaught failures we
simply stop trying that job and move on — the server-side reaper / manual
operator can clean up stuck 'running' rows.

Run on:
  * Sandbox (5.78.206.88) as a CPU worker for ML jobs.
  * User's laptop as a GPU worker for DL jobs (RTX 5060).

Config (env vars, or a .env in the same dir):
    MARKET_AI_SERVER_URL          Base URL (e.g. https://binmuhayyaai.com)
    MARKET_AI_WORKER_TOKEN        Shared secret (matches server .env)
    MARKET_AI_WORKER_ID           Unique id (default: hostname-pid)
    MARKET_AI_WORKER_MODEL_TYPES  Comma list: "dl,ml" or "ml" (default: "ml")
    MARKET_AI_WORKER_POLL_SECONDS Poll interval (default: 8)
    MARKET_AI_TORCH_DEVICE        "cuda" | "cpu" | "auto" (default: auto)
    MARKET_AI_ML_N_JOBS           sklearn n_jobs (default: -1)
    MARKET_AI_WORKER_VERIFY_SSL   "1" | "0" (default: 1)

Requires the same market-ai-dashboard repo checked out locally (the daemon
imports ``backend.app.services.ml_lab`` / ``dl_lab`` to do the actual work).
"""

from __future__ import annotations

import json
import logging
import os
import platform
import signal
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

import requests


LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger("trainer_daemon_v2")


def _env(name: str, default: str | None = None, required: bool = False) -> str | None:
    val = os.environ.get(name, default)
    if val is not None:
        val = str(val).strip()
    if required and not val:
        log.error("Missing required env var: %s", name)
        sys.exit(2)
    return val


SERVER_URL = (_env("MARKET_AI_SERVER_URL", required=True) or "").rstrip("/")
WORKER_TOKEN = _env("MARKET_AI_WORKER_TOKEN", required=True)
WORKER_ID = _env("MARKET_AI_WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"
WORKER_HOSTNAME = socket.gethostname()
MODEL_TYPES = [
    t.strip().lower()
    for t in (_env("MARKET_AI_WORKER_MODEL_TYPES") or "ml").split(",")
    if t.strip()
]
POLL_SECONDS = max(2, int(_env("MARKET_AI_WORKER_POLL_SECONDS") or "8"))
VERIFY_SSL = (_env("MARKET_AI_WORKER_VERIFY_SSL") or "1") not in {"0", "false", "no"}

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


_session = requests.Session()
_session.headers.update({"Authorization": f"Bearer {WORKER_TOKEN}"})


def _get(path: str, params: dict | None = None, timeout: int = 15) -> requests.Response:
    return _session.get(f"{SERVER_URL}{path}", params=params or {}, timeout=timeout, verify=VERIFY_SSL)


def _post_json(path: str, payload: dict, timeout: int = 30) -> requests.Response:
    return _session.post(f"{SERVER_URL}{path}", json=payload, timeout=timeout, verify=VERIFY_SSL)


def _post_multipart(path: str, data: dict, files: dict, timeout: int = 300) -> requests.Response:
    return _session.post(f"{SERVER_URL}{path}", data=data, files=files, timeout=timeout, verify=VERIFY_SSL)


# ── Training ──────────────────────────────────────────────────────────────

def _run_training(model_type: str, payload: dict) -> dict:
    os.environ.setdefault("MARKET_AI_TORCH_DEVICE", os.environ.get("MARKET_AI_TORCH_DEVICE", "auto"))
    os.environ.setdefault("MARKET_AI_ML_N_JOBS", os.environ.get("MARKET_AI_ML_N_JOBS", "-1"))
    if model_type == "dl":
        from backend.app.services.dl_lab import train_sequence_model
        return train_sequence_model(**(payload or {}))
    if model_type == "ml":
        from backend.app.services.ml_lab import train_baseline_models
        return train_baseline_models(**(payload or {}))
    raise ValueError(f"Unsupported model_type: {model_type}")


# ── Protocol ──────────────────────────────────────────────────────────────

def _peek_next(model_type: str) -> dict | None:
    try:
        resp = _get("/api/training/jobs/next-queued", {"model_type": model_type})
    except Exception as exc:
        log.warning("peek %s failed: %s", model_type, exc)
        return None
    if resp.status_code == 401:
        log.error("token rejected (401). Stopping."); _shutdown.set(); return None
    if resp.status_code == 503:
        log.error("worker protocol disabled on server (503). Sleeping 60s.")
        _shutdown.wait(60); return None
    if resp.status_code != 200:
        log.warning("peek %s returned %s: %s", model_type, resp.status_code, resp.text[:200])
        return None
    body = resp.json() or {}
    return body.get("job")


def _claim(job_id: str) -> dict | None:
    try:
        resp = _post_json(
            f"/api/training/jobs/{job_id}/claim",
            {"worker_id": WORKER_ID, "worker_hostname": WORKER_HOSTNAME},
        )
    except Exception as exc:
        log.warning("claim %s failed: %s", job_id, exc)
        return None
    if resp.status_code == 200:
        return (resp.json() or {}).get("job")
    if resp.status_code in (404, 409):
        log.info("claim %s lost (%s): %s", job_id, resp.status_code, resp.text[:200])
        return None
    log.warning("claim %s unexpected %s: %s", job_id, resp.status_code, resp.text[:200])
    return None


def _upload(job_id: str, model_type: str, result: dict, original_payload: dict) -> None:
    run_id = result.get("run_id") or ""
    artifact_path = result.get("artifact_path") or ""
    model_name = result.get("model_name") or ("gru_sequence" if model_type == "dl" else "baseline_ml")
    metrics = result.get("metrics") or {}
    rows = result.get("rows") or {}
    if not run_id or not artifact_path or not Path(artifact_path).exists():
        raise RuntimeError(
            f"Training result missing run_id/artifact_path or file doesn't exist: "
            f"run_id={run_id!r} artifact_path={artifact_path!r}"
        )
    set_active = bool(original_payload.get("set_active", True))
    filename = Path(artifact_path).name
    with Path(artifact_path).open("rb") as fh:
        files = {"artifact_file": (filename, fh, "application/octet-stream")}
        data = {
            "worker_id": WORKER_ID,
            "run_id": run_id,
            "model_name": model_name,
            "metrics_json": json.dumps(metrics, default=str),
            "rows_json": json.dumps(rows, default=str),
            "config_json": json.dumps(original_payload or {}, default=str),
            "set_active": "true" if set_active else "false",
        }
        resp = _post_multipart(f"/api/training/jobs/{job_id}/artifact", data=data, files=files)
    if resp.status_code != 200:
        raise RuntimeError(f"Upload failed ({resp.status_code}): {resp.text[:500]}")
    log.info("job %s uploaded (run_id=%s, artifact=%s)", job_id, run_id, filename)


# ── Main loop ─────────────────────────────────────────────────────────────

_shutdown = threading.Event()


def _handle_job(job: dict) -> None:
    job_id = job.get("job_id") or job.get("id")
    model_type = (job.get("model_type") or "ml").strip().lower()
    payload = job.get("payload") or job.get("payload_json") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    log.info("training job_id=%s model_type=%s", job_id, model_type)
    t0 = time.time()
    try:
        result = _run_training(model_type, payload)
        if not isinstance(result, dict):
            raise RuntimeError(f"Training returned non-dict: {type(result).__name__}")
        if result.get("error"):
            raise RuntimeError(f"Training error: {result['error']}")
        _upload(job_id, model_type, result, payload)
        log.info("job %s done in %.1fs", job_id, time.time() - t0)
    except Exception as exc:
        log.error("job %s failed after %.1fs: %s\n%s", job_id, time.time() - t0, exc, traceback.format_exc()[-2000:])


def _bootstrap_log() -> None:
    device = "cpu"
    try:
        import torch  # type: ignore
        if torch.cuda.is_available():
            device = f"cuda:{torch.cuda.get_device_name(0)} ({round(torch.cuda.get_device_properties(0).total_memory/1e9,1)}GB)"
    except Exception:
        pass
    log.info(
        "trainer_daemon_v2 starting | worker_id=%s | host=%s | python=%s | torch=%s | types=%s | server=%s",
        WORKER_ID, WORKER_HOSTNAME, platform.python_version(), device, MODEL_TYPES, SERVER_URL,
    )


def _signal_handler(signum, _frame):
    log.info("received signal %s, stopping…", signum)
    _shutdown.set()


def main() -> int:
    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _signal_handler)
    _bootstrap_log()

    # Initial handshake — warn early on misconfig.
    try:
        r = _get("/api/training/jobs/next-queued", {"model_type": MODEL_TYPES[0]})
        if r.status_code == 401:
            log.error("token rejected on startup. Aborting."); return 2
        if r.status_code == 503:
            log.error("server reports protocol disabled. Check MARKET_AI_WORKER_TOKEN."); return 2
        log.info("initial handshake OK (%s)", r.status_code)
    except Exception as exc:
        log.error("initial handshake failed: %s — will retry in loop.", exc)

    while not _shutdown.is_set():
        for mt in MODEL_TYPES:
            job = _peek_next(mt)
            if not job:
                continue
            jid = job.get("job_id") or job.get("id")
            if not jid:
                continue
            claimed = _claim(jid)
            if not claimed:
                continue
            _handle_job(claimed)
            break
        else:
            _shutdown.wait(POLL_SECONDS)
    log.info("trainer_daemon_v2 stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
