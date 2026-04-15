#!/usr/bin/env python3
"""Remote GPU training worker — runs on the laptop (RTX 5060) and trains
jobs that the server (46.225.87.252) has queued.

=============================================================================
 HOW IT WORKS
=============================================================================

  Server                                           Laptop (this daemon)
  ──────                                           ───────────────────

  TrainingJob row in DB, status='queued'
                │
                │   every 5s:
                │   GET /api/training/jobs/next-queued
                │◀──────────────────────────────────────────────
                │
                │   if job present:
                │   POST /api/training/jobs/{id}/claim
                │──────────────────────────────────────────────▶
                │   status='running', worker_id set
                │
                │                                  train locally on CUDA
                │                                  (imports train_dl_models /
                │                                   train_ml_models from the
                │                                   backend package, reuses
                │                                   the SAME training logic so
                │                                   artifacts are compatible)
                │
                │   POST /api/training/jobs/{id}/artifact
                │   multipart: artifact_file + metrics_json + rows_json
                │◀──────────────────────────────────────────────
                │   server saves artifact, creates ModelRun,
                │   marks job 'completed'

  Auth: every request carries `Authorization: Bearer <MARKET_AI_WORKER_TOKEN>`.
  The same token must be set on BOTH the server (backend .env) and the laptop
  (MARKET_AI_WORKER_TOKEN in this daemon's env).

=============================================================================
 INSTALL ON THE LAPTOP
=============================================================================

  1. Install Tailscale: https://tailscale.com/download — sign in with the
     same account used on the server. Confirm the laptop shows up in the
     Tailscale admin with IP 100.123.117.116.

  2. Copy the repo onto the laptop (same `app/` layout as on the server)
     so this daemon can import the training package:
         git clone <repo> C:\\market-ai-dashboard
         cd C:\\market-ai-dashboard\\app

  3. Create a venv and install deps + PyTorch nightly with CUDA for the
     RTX 5060 (sm_120 / Blackwell):
         python -m venv .venv
         .venv\\Scripts\\activate
         pip install --pre torch torchvision torchaudio \\
             --index-url https://download.pytorch.org/whl/nightly/cu128
         pip install -r backend/requirements.txt   # or minimally:
         pip install fastapi uvicorn sqlalchemy yfinance pandas numpy \\
             requests python-dotenv pydantic

  4. Create `trainer_daemon.env` next to this script with:
         MARKET_AI_SERVER_URL=http://<server-tailscale-ip>:8000
         MARKET_AI_WORKER_TOKEN=<same shared secret as the server>
         MARKET_AI_WORKER_ID=laptop-rtx5060
         MARKET_AI_TORCH_DEVICE=cuda
         # optional:
         MARKET_AI_WORKER_POLL_SECONDS=5
         MARKET_AI_WORKER_MODEL_TYPE=   # 'dl', 'ml', or empty for any

  5. Run it (from the `app/` directory so imports resolve):
         cd app
         python backend/trainer_daemon.py

     It will poll the server every 5s and pick up jobs automatically.

=============================================================================
 SERVER SIDE CHECKLIST (so the daemon has something to pick up)
=============================================================================

  In the backend .env (on the server):

      MARKET_AI_REMOTE_TRAINING_ENABLED=1     # disables local subprocess
      MARKET_AI_WORKER_TOKEN=<shared secret>  # must match the laptop token

  Restart the backend container. New `POST /api/training/jobs/start` calls
  will now leave jobs in 'queued' state instead of launching a local
  subprocess — the daemon will grab them.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError as exc:
    raise SystemExit(
        "trainer_daemon requires the `requests` package. Install it with "
        "`pip install requests` before running this script."
    ) from exc


# ── Config loading ─────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_CANDIDATES = [
    SCRIPT_DIR / "trainer_daemon.env",
    SCRIPT_DIR.parent / "trainer_daemon.env",
    Path.cwd() / "trainer_daemon.env",
]

def _load_env_file() -> None:
    """Load the first `trainer_daemon.env` found in SCRIPT_DIR / parent / cwd.

    Kept dependency-free — we don't want to require python-dotenv on the
    laptop just to read KEY=VALUE lines.
    """
    for candidate in ENV_CANDIDATES:
        if not candidate.exists():
            continue
        try:
            for raw in candidate.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
            print(f"[trainer] loaded env from {candidate}")
            return
        except Exception as exc:
            print(f"[trainer] WARN: could not parse {candidate}: {exc}")
    print("[trainer] no trainer_daemon.env found — relying on process env only")


_load_env_file()


SERVER_URL = os.environ.get("MARKET_AI_SERVER_URL", "").rstrip("/")
WORKER_TOKEN = os.environ.get("MARKET_AI_WORKER_TOKEN", "").strip()
WORKER_ID = os.environ.get("MARKET_AI_WORKER_ID", "").strip() or f"worker-{socket.gethostname()}"
WORKER_HOSTNAME = os.environ.get("MARKET_AI_WORKER_HOSTNAME", "").strip() or socket.gethostname()
POLL_SECONDS = max(2, int(os.environ.get("MARKET_AI_WORKER_POLL_SECONDS", "5")))
MODEL_TYPE_FILTER = os.environ.get("MARKET_AI_WORKER_MODEL_TYPE", "").strip().lower() or None
REQUEST_TIMEOUT = float(os.environ.get("MARKET_AI_WORKER_HTTP_TIMEOUT", "30"))
UPLOAD_TIMEOUT = float(os.environ.get("MARKET_AI_WORKER_UPLOAD_TIMEOUT", "600"))

if not SERVER_URL:
    raise SystemExit("MARKET_AI_SERVER_URL is required (example: http://100.x.x.x:8000).")
if not WORKER_TOKEN:
    raise SystemExit("MARKET_AI_WORKER_TOKEN is required (shared secret with backend).")


# ── Logging ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [trainer] %(levelname)s %(message)s",
)
log = logging.getLogger("trainer_daemon")


def _print_banner() -> None:
    print("=" * 72)
    print(" Market-AI remote training worker")
    print("=" * 72)
    print(f"  server         : {SERVER_URL}")
    print(f"  worker_id      : {WORKER_ID}")
    print(f"  worker_host    : {WORKER_HOSTNAME}")
    print(f"  poll_every     : {POLL_SECONDS}s")
    print(f"  model_type     : {MODEL_TYPE_FILTER or 'any'}")
    print(f"  python         : {sys.version.split()[0]} ({platform.python_implementation()})")
    try:
        import torch  # deferred so the banner still prints on torch-less installs
        print(f"  torch          : {torch.__version__}")
        if torch.cuda.is_available():
            dev_name = torch.cuda.get_device_name(0)
            print(f"  cuda           : YES — {dev_name}")
        else:
            print("  cuda           : NO  — will train on CPU (slow)")
    except Exception as exc:
        print(f"  torch          : NOT INSTALLED ({exc})")
    print("=" * 72)


# ── HTTP helpers ───────────────────────────────────────────────────────────

_session = requests.Session()
_session.headers.update({"Authorization": f"Bearer {WORKER_TOKEN}"})

# Transport stability: Tailscale / uvicorn occasionally drop idle keep-alive
# connections, which surfaces as `RemoteDisconnected('Remote end closed
# connection without response')` on the next poll. Mount a retry-enabled
# adapter so urllib3 silently reconnects and re-issues the request instead of
# bubbling the transient error up to the polling loop.
_retry = Retry(
    total=5,
    connect=5,
    read=5,
    status=3,
    backoff_factor=0.5,
    status_forcelist=(502, 503, 504),
    allowed_methods=frozenset(("GET", "POST")),
    raise_on_status=False,
    respect_retry_after_header=True,
)
_adapter = HTTPAdapter(max_retries=_retry, pool_connections=4, pool_maxsize=4)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)


def _get(path: str, **kwargs: Any) -> requests.Response:
    return _session.get(f"{SERVER_URL}{path}", timeout=REQUEST_TIMEOUT, **kwargs)


def _post(path: str, **kwargs: Any) -> requests.Response:
    timeout = kwargs.pop("timeout", REQUEST_TIMEOUT)
    return _session.post(f"{SERVER_URL}{path}", timeout=timeout, **kwargs)


def _poll_next_queued() -> dict | None:
    params = {}
    if MODEL_TYPE_FILTER:
        params["model_type"] = MODEL_TYPE_FILTER
    try:
        resp = _get("/api/training/jobs/next-queued", params=params)
    except requests.RequestException as exc:
        log.warning("poll failed: %s", exc)
        return None
    if resp.status_code == 503:
        log.error("server disabled the worker protocol (set MARKET_AI_WORKER_TOKEN on the backend). Sleeping.")
        time.sleep(30)
        return None
    if resp.status_code != 200:
        log.warning("poll returned %s: %s", resp.status_code, resp.text[:200])
        return None
    data = resp.json()
    return data.get("job")


def _claim_job(job_id: str) -> dict | None:
    body = {"worker_id": WORKER_ID, "worker_hostname": WORKER_HOSTNAME}
    if MODEL_TYPE_FILTER:
        body["model_type"] = MODEL_TYPE_FILTER
    try:
        resp = _post(f"/api/training/jobs/{job_id}/claim", json=body)
    except requests.RequestException as exc:
        log.warning("claim(%s) failed: %s", job_id, exc)
        return None
    if resp.status_code == 200:
        data = resp.json()
        return data.get("job")
    if resp.status_code in (404, 409):
        # Another worker grabbed it, or the job was deleted — just skip.
        log.info("claim(%s) skipped (%s): %s", job_id, resp.status_code, resp.text[:120])
        return None
    log.warning("claim(%s) returned %s: %s", job_id, resp.status_code, resp.text[:200])
    return None


def _send_heartbeat(job_id: str) -> None:
    """Best-effort heartbeat against the existing /training/worker endpoint.

    This keeps backward compatibility with the stale-worker reconciler on the
    server (release_stale_remote_jobs). We don't fail the job just because a
    heartbeat request dropped — the training itself is the source of truth.
    """
    try:
        _post(
            f"/api/training/worker/jobs/{job_id}/heartbeat",
            json={"worker_id": WORKER_ID},
        )
    except requests.RequestException as exc:
        log.debug("heartbeat(%s) dropped: %s", job_id, exc)


def _report_failure(job_id: str, error_message: str) -> None:
    try:
        _post(
            f"/api/training/worker/jobs/{job_id}/fail",
            json={"worker_id": WORKER_ID, "error_message": error_message[:3900]},
        )
    except requests.RequestException as exc:
        log.error("fail-report(%s) dropped: %s — server reconciler will mark it stale.", job_id, exc)


def _upload_artifact(
    job_id: str,
    *,
    run_id: str,
    model_name: str,
    artifact_path: Path,
    metrics: dict,
    rows: dict,
    config: dict,
    set_active: bool = True,
) -> dict | None:
    data = {
        "worker_id": WORKER_ID,
        "run_id": run_id,
        "model_name": model_name,
        "metrics_json": json.dumps(metrics, default=str),
        "rows_json": json.dumps(rows, default=str),
        "config_json": json.dumps(config, default=str),
        "set_active": "true" if set_active else "false",
    }
    with artifact_path.open("rb") as handle:
        files = {"artifact_file": (artifact_path.name, handle, "application/octet-stream")}
        resp = _post(
            f"/api/training/jobs/{job_id}/artifact",
            data=data,
            files=files,
            timeout=UPLOAD_TIMEOUT,
        )
    if resp.status_code != 200:
        log.error("artifact upload failed (%s): %s", resp.status_code, resp.text[:300])
        return None
    return resp.json()


# ── Training bridge (reuse server-side code) ──────────────────────────────
#
# We import the existing `train_dl_models` / `train_ml_models` from the
# backend package so the artifact layout + metrics keys are identical to
# locally-trained runs. This assumes the laptop has the same repo checked
# out and its `app/` directory is on PYTHONPATH.

def _import_trainers():
    try:
        from backend.app.application.model_lifecycle.service import (
            train_dl_models,
            train_ml_models,
        )
        from backend.app.db.session import init_db
    except ImportError as exc:
        raise SystemExit(
            "Could not import the training package. Make sure you run this "
            "script with the market-ai-dashboard `app/` directory on "
            "PYTHONPATH (cd app && python backend/trainer_daemon.py). "
            f"Import error: {exc}"
        ) from exc
    return train_dl_models, train_ml_models, init_db


def _run_training(job: dict) -> tuple[Path, dict]:
    """Execute the claimed job locally and return (artifact_path, result).

    `result` matches what the server's /artifact endpoint expects:
      run_id, model_type, model_name, artifact_path, metrics, rows, config.
    """
    model_type = (job.get("model_type") or "").strip().lower()
    payload = job.get("payload") or {}

    train_dl_models, train_ml_models, init_db = _import_trainers()

    # Ensure the local SQLAlchemy session used inside train_*_models() has a
    # DB to talk to (SQLite default). The laptop's local DB is ephemeral —
    # the authoritative ModelRun row gets created on the SERVER when the
    # artifact is uploaded back.
    try:
        init_db(run_migrations=False)
    except Exception as exc:
        log.warning("init_db() non-fatal warning: %s", exc)

    log.info("▶ training model_type=%s payload_keys=%s", model_type, sorted(payload.keys()))
    if model_type == "dl":
        result = train_dl_models(**payload)
    elif model_type == "ml":
        result = train_ml_models(**payload)
    else:
        raise RuntimeError(f"Unsupported model_type '{model_type}' in job payload")

    if not isinstance(result, dict):
        raise RuntimeError(f"Training function returned unexpected type: {type(result).__name__}")
    if result.get("error"):
        raise RuntimeError(f"Training reported error: {result['error']}")
    artifact_path_str = result.get("artifact_path") or result.get("checkpoint_path")
    if not artifact_path_str:
        raise RuntimeError(f"Training result missing 'artifact_path': {sorted(result.keys())}")
    artifact_path = Path(artifact_path_str)
    if not artifact_path.exists():
        raise RuntimeError(f"Artifact file does not exist: {artifact_path}")
    return artifact_path, result


# ── Main loop ──────────────────────────────────────────────────────────────

def _handle_one_job(job: dict) -> None:
    job_id = job.get("job_id")
    if not job_id:
        log.warning("received job with no job_id: %r", job)
        return

    log.info("◆ claiming job %s (model_type=%s)", job_id, job.get("model_type"))
    claimed = _claim_job(job_id)
    if claimed is None:
        return  # skipped or already taken

    started_at = time.monotonic()
    try:
        _send_heartbeat(job_id)
        artifact_path, result = _run_training(claimed)
        elapsed = time.monotonic() - started_at
        log.info("✓ training finished in %.1fs — artifact=%s", elapsed, artifact_path)

        run_id = result.get("run_id") or f"dl-{datetime.utcnow():%Y%m%d%H%M%S}"
        model_name = result.get("model_name") or (
            "gru_sequence" if claimed.get("model_type") == "dl" else "ensemble"
        )
        metrics = result.get("metrics") or {}
        metrics.setdefault("validation_macro_f1", result.get("validation_macro_f1"))
        metrics.setdefault("test_accuracy", result.get("test_accuracy"))
        metrics.setdefault("best_model_name", model_name)
        rows = result.get("rows") or {
            "train": result.get("train_rows"),
            "validation": result.get("validation_rows"),
            "test": result.get("test_rows"),
        }
        config = result.get("config") or (claimed.get("payload") or {})

        upload = _upload_artifact(
            job_id,
            run_id=run_id,
            model_name=model_name,
            artifact_path=artifact_path,
            metrics=metrics,
            rows=rows,
            config=config,
            set_active=True,
        )
        if upload is None:
            raise RuntimeError("artifact upload failed — see previous error")
        log.info("✓ job %s COMPLETED (run_id=%s)", job_id, upload.get("run_id"))

    except Exception as exc:  # pragma: no cover — this is the job's safety net
        log.exception("job %s FAILED", job_id)
        _report_failure(job_id, f"{type(exc).__name__}: {exc}")


def main() -> int:
    _print_banner()
    # Initial reachability check so operators see a clear error instead of
    # the daemon silently looping on connection failures.
    try:
        health = _get("/health")
        log.info("server /health → %s", health.status_code)
    except requests.RequestException as exc:
        log.error("cannot reach %s — %s. Check Tailscale / firewall. Will keep trying.", SERVER_URL, exc)

    log.info("entering polling loop (every %ds)…", POLL_SECONDS)
    while True:
        job = _poll_next_queued()
        if job is None:
            time.sleep(POLL_SECONDS)
            continue
        _handle_one_job(job)
        # Immediately poll again in case more jobs are queued.


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n[trainer] shutting down on Ctrl-C")
        raise SystemExit(0)
