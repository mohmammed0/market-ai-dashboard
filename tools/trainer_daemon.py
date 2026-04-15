"""Remote GPU trainer daemon for market-ai-dashboard.

Runs on a machine with CUDA (e.g. laptop with RTX 5060). Polls the server
for queued training jobs, executes them locally with GPU, and uploads the
resulting artifact + metrics back to the server.

Configuration via environment variables (or a .env file in the same dir):

    MARKET_AI_SERVER_URL          Base URL, e.g. https://binmuhayyaai.com
    MARKET_AI_WORKER_TOKEN        Shared secret matching server-side env
    MARKET_AI_WORKER_ID           Unique ID for this worker (default: hostname)
    MARKET_AI_WORKER_MODEL_TYPES  Comma list: "dl,ml" or "dl" (default: "dl,ml")
    MARKET_AI_WORKER_POLL_SECONDS Poll interval (default: 5)
    MARKET_AI_TORCH_DEVICE        "cuda" | "cpu" | "auto" (default: auto)
    MARKET_AI_ML_N_JOBS           sklearn n_jobs for ML jobs (default: -1)
    MARKET_AI_WORKER_VERIFY_SSL   "1" or "0" (default: 1)

Usage:
    # First-time setup (Windows PowerShell):
    cd C:\\market-ai\\app
    .\\venv\\Scripts\\Activate.ps1
    $env:MARKET_AI_SERVER_URL="https://binmuhayyaai.com"
    $env:MARKET_AI_WORKER_TOKEN="<token from server .env>"
    python tools\\trainer_daemon.py

The daemon expects this repo to be a full checkout of market-ai-dashboard
(so backend.app.services.{dl_lab,ml_lab} are importable). It imports the
same training functions the server uses — no code duplication.
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


# ── Config ─────────────────────────────────────────────────────────────────

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger("trainer_daemon")


def _get_env(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.environ.get(name, default)
    if value is not None:
        value = str(value).strip()
    if required and not value:
        log.error("Missing required env var: %s", name)
        sys.exit(2)
    return value


SERVER_URL = (_get_env("MARKET_AI_SERVER_URL", required=True) or "").rstrip("/")
WORKER_TOKEN = _get_env("MARKET_AI_WORKER_TOKEN", required=True)
WORKER_ID = _get_env("MARKET_AI_WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"
WORKER_HOSTNAME = socket.gethostname()
MODEL_TYPES = [t.strip().lower() for t in (_get_env("MARKET_AI_WORKER_MODEL_TYPES") or "dl,ml").split(",") if t.strip()]
POLL_SECONDS = max(2, int(_get_env("MARKET_AI_WORKER_POLL_SECONDS") or "5"))
VERIFY_SSL = (_get_env("MARKET_AI_WORKER_VERIFY_SSL") or "1") not in {"0", "false", "no"}
HEARTBEAT_SECONDS = 30

# Ensure repo root is importable so `from backend.app.services ...` works.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ── HTTP helpers ───────────────────────────────────────────────────────────

_session = requests.Session()
_session.headers.update({"Authorization": f"Bearer {WORKER_TOKEN}"})


def _url(path: str) -> str:
    return f"{SERVER_URL}{path}"


def _post_json(path: str, payload: dict, timeout: int = 30) -> requests.Response:
    return _session.post(_url(path), json=payload, timeout=timeout, verify=VERIFY_SSL)


def _post_multipart(path: str, data: dict, files: dict, timeout: int = 300) -> requests.Response:
    return _session.post(_url(path), data=data, files=files, timeout=timeout, verify=VERIFY_SSL)


# ── Heartbeat thread ───────────────────────────────────────────────────────

class Heartbeat:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"heartbeat-{job_id}", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(HEARTBEAT_SECONDS):
            try:
                resp = _post_json(
                    f"/api/training/worker/jobs/{self.job_id}/heartbeat",
                    {"worker_id": WORKER_ID},
                    timeout=15,
                )
                if resp.status_code != 200:
                    log.warning("heartbeat %s returned %s: %s", self.job_id, resp.status_code, resp.text[:200])
            except Exception as exc:
                log.warning("heartbeat %s failed: %s", self.job_id, exc)


# ── Training execution ────────────────────────────────────────────────────

def _run_training(model_type: str, payload: dict) -> dict:
    """Dispatch the job to the local training function. Returns server-ready result."""
    # Force worker-specific env hints before import (dl_lab reads MARKET_AI_TORCH_DEVICE).
    os.environ.setdefault("MARKET_AI_TORCH_DEVICE", os.environ.get("MARKET_AI_TORCH_DEVICE", "auto"))
    os.environ.setdefault("MARKET_AI_ML_N_JOBS", os.environ.get("MARKET_AI_ML_N_JOBS", "-1"))

    if model_type == "dl":
        from backend.app.services.dl_lab import train_sequence_model
        return train_sequence_model(**(payload or {}))
    if model_type == "ml":
        from backend.app.services.ml_lab import train_baseline_models
        return train_baseline_models(**(payload or {}))
    raise ValueError(f"Unsupported model_type: {model_type}")


def _upload_result(job_id: str, model_type: str, result: dict, original_payload: dict) -> None:
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
        resp = _post_multipart(f"/api/training/worker/jobs/{job_id}/complete", data=data, files=files)
    if resp.status_code != 200:
        raise RuntimeError(f"Upload failed ({resp.status_code}): {resp.text[:500]}")
    log.info("job %s uploaded successfully (run_id=%s)", job_id, run_id)


def _report_fail(job_id: str, error_message: str) -> None:
    try:
        _post_json(
            f"/api/training/worker/jobs/{job_id}/fail",
            {"worker_id": WORKER_ID, "error_message": error_message[:3800]},
            timeout=15,
        )
    except Exception as exc:
        log.error("failed to report job %s failure: %s", job_id, exc)


# ── Main loop ─────────────────────────────────────────────────────────────

_shutdown = threading.Event()


def _signal_handler(signum, _frame):
    log.info("received signal %s, shutting down…", signum)
    _shutdown.set()


def _claim_next_job() -> dict | None:
    # Try each allowed model_type in the configured order.
    for mt in MODEL_TYPES:
        try:
            resp = _post_json(
                "/api/training/worker/next-job",
                {
                    "worker_id": WORKER_ID,
                    "worker_hostname": WORKER_HOSTNAME,
                    "model_type": mt,
                },
                timeout=15,
            )
        except Exception as exc:
            log.warning("next-job poll for %s failed: %s", mt, exc)
            continue
        if resp.status_code == 503:
            log.error("server reports worker protocol disabled (503). Sleeping 60s.")
            _shutdown.wait(60)
            return None
        if resp.status_code == 401:
            log.error("worker token rejected (401). Check MARKET_AI_WORKER_TOKEN. Stopping.")
            _shutdown.set()
            return None
        if resp.status_code != 200:
            log.warning("next-job %s returned %s: %s", mt, resp.status_code, resp.text[:300])
            continue
        body = resp.json() or {}
        if body.get("claimed") and body.get("job"):
            return body["job"]
    return None


def _handle_job(job: dict) -> None:
    job_id = job["job_id"]
    model_type = job["model_type"]
    payload = job.get("payload") or {}
    log.info("claimed job_id=%s model_type=%s", job_id, model_type)

    hb = Heartbeat(job_id)
    hb.start()
    try:
        result = _run_training(model_type, payload)
        if not isinstance(result, dict):
            raise RuntimeError(f"Training returned non-dict: {type(result).__name__}")
        if result.get("error"):
            raise RuntimeError(f"Training error: {result['error']}")
        _upload_result(job_id, model_type, result, payload)
    except Exception as exc:
        tb = traceback.format_exc()
        log.error("job %s failed: %s\n%s", job_id, exc, tb)
        _report_fail(job_id, f"{exc}\n\n{tb[-2000:]}")
    finally:
        hb.stop()


def _bootstrap_log() -> None:
    device_info = "unknown"
    try:
        import torch  # type: ignore
        if torch.cuda.is_available():
            device_info = f"cuda:{torch.cuda.get_device_name(0)} ({round(torch.cuda.get_device_properties(0).total_memory/1e9,1)}GB)"
        else:
            device_info = "cpu"
    except Exception:
        pass
    log.info(
        "trainer_daemon starting | worker_id=%s | host=%s | python=%s | torch=%s | types=%s | server=%s",
        WORKER_ID,
        WORKER_HOSTNAME,
        platform.python_version(),
        device_info,
        MODEL_TYPES,
        SERVER_URL,
    )


def main() -> int:
    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _signal_handler)

    _bootstrap_log()

    # Initial ping to verify server + token early.
    try:
        resp = _post_json(
            "/api/training/worker/next-job",
            {"worker_id": WORKER_ID, "worker_hostname": WORKER_HOSTNAME, "model_type": MODEL_TYPES[0]},
            timeout=10,
        )
        if resp.status_code == 401:
            log.error("worker token rejected on startup. Aborting.")
            return 2
        if resp.status_code == 503:
            log.error("server reports worker protocol disabled. Ensure MARKET_AI_WORKER_TOKEN is set on the server.")
            return 2
        log.info("initial handshake OK (%s)", resp.status_code)
        body = resp.json() or {}
        if body.get("claimed"):
            _handle_job(body["job"])
    except Exception as exc:
        log.error("initial handshake failed: %s — will retry in loop.", exc)

    while not _shutdown.is_set():
        try:
            job = _claim_next_job()
            if job:
                _handle_job(job)
            else:
                _shutdown.wait(POLL_SECONDS)
        except Exception as exc:
            log.error("main loop error: %s", exc)
            _shutdown.wait(POLL_SECONDS * 2)
    log.info("trainer_daemon stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
