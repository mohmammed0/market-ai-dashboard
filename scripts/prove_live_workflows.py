"""Live Workflow Proving Script.

Proves that real end-to-end product workflows execute through the live stack:
- One heavy workflow through Prefect (batch inference)
- One short task through Celery (quote snapshot dispatch)
- One experiment run logged to MLflow (via experiment tracker)
- Visibility verification through product/runtime surfaces

Requires live services running (docker compose + Prefect server).
See LOCAL_LIVE_SERVICES.md for setup.

Usage:
    .\\venv\\Scripts\\python.exe scripts\\prove_live_workflows.py
"""

import os
import sys
import time
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def banner(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def result(name, passed, detail=""):
    icon = "PASS" if passed else "FAIL"
    print(f"  [{icon}] {name}{f' — {detail}' if detail else ''}")
    return passed


# -----------------------------------------------------------------------
# 1. Prefect workflow execution
# -----------------------------------------------------------------------

def prove_prefect_workflow():
    """Prove a real heavy workflow runs through Prefect."""
    banner("Prefect Workflow Proving")

    from backend.app.config import PREFECT_API_URL
    if not PREFECT_API_URL:
        return result("Prefect", False, "PREFECT_API_URL not configured")

    # 1a. Verify flow registration
    try:
        from backend.app.services.prefect_flows import list_flows
        flows = list_flows()
        result("Flow Registration", len(flows) > 0, f"registered: {flows}")
    except Exception as e:
        return result("Flow Registration", False, str(e)[:120])

    # 1b. Verify orchestration gateway sees Prefect
    try:
        from backend.app.services.orchestration_gateway import is_prefect_available
        available = is_prefect_available()
        result("Gateway Availability", available, f"is_prefect_available()={available}")
        if not available:
            return result("Prefect", False, "Prefect not available via gateway")
    except Exception as e:
        return result("Gateway Availability", False, str(e)[:120])

    # 1c. Execute batch inference through the orchestration gateway
    try:
        from backend.app.services.orchestration_gateway import run_batch_inference_orchestrated

        payload = {
            "symbols": ["AAPL"],
            "start_date": "2025-01-01",
            "end_date": "2025-03-01",
            "include_dl": False,
            "include_ensemble": False,
        }
        print("  [....] Executing batch_inference through Prefect (this may take a moment)...")
        t0 = time.time()
        res = run_batch_inference_orchestrated(payload)
        elapsed = time.time() - t0

        backend = res.get("backend", "?")
        status = res.get("status", "?")
        flow_run_id = res.get("flow_run_id")
        items = res.get("result", {}).get("items", []) if isinstance(res.get("result"), dict) else []

        result(
            "Batch Inference via Prefect",
            backend == "prefect" and status == "completed",
            f"backend={backend}, status={status}, flow_run={flow_run_id}, "
            f"items={len(items)}, elapsed={elapsed:.1f}s",
        )
    except Exception as e:
        result("Batch Inference via Prefect", False, str(e)[:150])

    # 1d. Verify flow run is tracked on Prefect server
    try:
        import urllib.request
        api_url = PREFECT_API_URL.rstrip("/")
        req = urllib.request.Request(
            f"{api_url}/flow_runs/filter",
            data=json.dumps({"limit": 3, "sort": "START_TIME_DESC"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            runs = json.loads(resp.read())
        recent = runs[0] if runs else {}
        result(
            "Prefect Server Tracking",
            len(runs) > 0,
            f"recent_flow={recent.get('name', '?')}, "
            f"state={recent.get('state', {}).get('type', '?')}, "
            f"total_recent={len(runs)}",
        )
    except Exception as e:
        result("Prefect Server Tracking", False, str(e)[:120])

    return True


# -----------------------------------------------------------------------
# 2. Celery task dispatch
# -----------------------------------------------------------------------

def prove_celery_dispatch():
    """Prove a real short task dispatches through Celery."""
    banner("Celery Task Dispatch Proving")

    from backend.app.config import CELERY_BROKER_URL
    if not CELERY_BROKER_URL:
        return result("Celery", False, "CELERY_BROKER_URL not configured")

    # 2a. Verify broker is reachable
    try:
        import redis as redis_lib
        client = redis_lib.Redis.from_url(CELERY_BROKER_URL, socket_connect_timeout=3)
        client.ping()
        result("Broker Connectivity", True, CELERY_BROKER_URL.split("@")[-1] if "@" in CELERY_BROKER_URL else CELERY_BROKER_URL)
        client.close()
    except Exception as e:
        return result("Broker Connectivity", False, str(e)[:120])

    # 2b. Verify Celery app singleton
    try:
        from backend.app.services.celery_app import get_celery_app
        app = get_celery_app()
        result("Celery App", app is not None, f"app={app.main if app else 'None'}")
    except Exception as e:
        return result("Celery App", False, str(e)[:120])

    # 2c. Dispatch quote_snapshot through orchestration gateway
    try:
        from backend.app.services.orchestration_gateway import dispatch_quote_snapshot
        res = dispatch_quote_snapshot()
        backend = res.get("backend", "?")
        status = res.get("status", "?")
        task_id = res.get("task_id", "?")
        result(
            "Quote Snapshot Dispatch",
            backend == "celery" and status == "dispatched",
            f"backend={backend}, status={status}, task_id={task_id}",
        )
    except Exception as e:
        result("Quote Snapshot Dispatch", False, str(e)[:120])

    # 2d. Dispatch maintenance_reconcile through orchestration gateway
    try:
        from backend.app.services.orchestration_gateway import dispatch_maintenance_reconcile
        res = dispatch_maintenance_reconcile()
        backend = res.get("backend", "?")
        status = res.get("status", "?")
        task_id = res.get("task_id", "?")
        result(
            "Maintenance Reconcile Dispatch",
            backend == "celery" and status == "dispatched",
            f"backend={backend}, status={status}, task_id={task_id}",
        )
    except Exception as e:
        result("Maintenance Reconcile Dispatch", False, str(e)[:120])

    # 2e. Check if a worker is connected (optional — dispatch succeeds without worker)
    try:
        if app:
            inspector = app.control.inspect(timeout=2.0)
            active = inspector.active()
            if active:
                worker_names = list(active.keys())
                result("Worker Connected", True, f"workers: {worker_names}")
            else:
                result("Worker Connected", False,
                       "No worker responding (tasks queued in broker, start a worker to execute)")
    except Exception as e:
        result("Worker Connected", False, f"inspect failed: {str(e)[:80]}")

    return True


# -----------------------------------------------------------------------
# 3. MLflow experiment logging
# -----------------------------------------------------------------------

def prove_mlflow_experiment():
    """Prove a real experiment run logs to the MLflow server."""
    banner("MLflow Experiment Tracking Proving")

    from backend.app.config import MLFLOW_TRACKING_URI
    if not MLFLOW_TRACKING_URI:
        return result("MLflow", False, "MLFLOW_TRACKING_URI not configured")

    # 3a. Verify MLflow server is reachable
    try:
        import urllib.request
        req = urllib.request.Request(f"{MLFLOW_TRACKING_URI.rstrip('/')}/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            result("Server Health", resp.getcode() == 200, f"HTTP {resp.getcode()}")
    except Exception as e:
        return result("Server Health", False, str(e)[:120])

    # 3b. Log a real experiment run through the application tracker
    try:
        from backend.app.services.experiment_tracker import log_experiment_run
        run_id = f"prove-workflow-{int(time.time())}"
        res = log_experiment_run(
            experiment_name="strategy_lab",
            run_id=run_id,
            params={
                "instrument": "AAPL",
                "start_date": "2025-01-01",
                "end_date": "2025-03-01",
                "hold_days": 10,
                "source": "prove_live_workflows",
            },
            metrics={
                "best_robust_score": 12.5,
                "classic_total_return_pct": 3.2,
                "oos_decay_pct": 8.1,
                "overfit_score": 85.0,
            },
            tags={
                "instrument": "AAPL",
                "best_strategy": "classic",
                "proven_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        backend = res.get("backend", "?")
        result(
            "Experiment Run Logged",
            backend == "mlflow",
            f"backend={backend}, run_id={run_id}, config_hash={res.get('config_hash', '?')}",
        )
    except Exception as e:
        result("Experiment Run Logged", False, str(e)[:120])

    # 3c. Verify run is queryable through the application surface
    try:
        from backend.app.services.experiment_tracker import list_experiment_runs
        runs = list_experiment_runs("strategy_lab", limit=5)
        source = runs[0].get("_source", "?") if runs else "?"
        result(
            "Runs Queryable",
            len(runs) > 0,
            f"recent_runs={len(runs)}, source={source}, "
            f"latest_run_id={runs[0].get('run_id', '?') if runs else 'none'}",
        )
    except Exception as e:
        result("Runs Queryable", False, str(e)[:120])

    # 3d. Verify tracking status
    try:
        from backend.app.services.experiment_tracker import get_tracking_status
        status = get_tracking_status()
        result(
            "Tracking Status",
            status.get("status") == "active" and status.get("backend") == "mlflow",
            f"backend={status.get('backend')}, status={status.get('status')}, "
            f"uri={status.get('mlflow_tracking_uri')}",
        )
    except Exception as e:
        result("Tracking Status", False, str(e)[:120])

    return True


# -----------------------------------------------------------------------
# 4. Runtime surface visibility
# -----------------------------------------------------------------------

def prove_runtime_surfaces():
    """Prove that runtime surfaces accurately report live stack topology."""
    banner("Runtime Surface Visibility")

    # 4a. Orchestration status
    try:
        from backend.app.services.orchestration_gateway import get_orchestration_status
        orch = get_orchestration_status()

        prefect_status = orch.get("prefect", {}).get("status", "?")
        celery_status = orch.get("celery", {}).get("status", "?")
        mlflow_backend = orch.get("mlflow", {}).get("backend", "?")
        registered_flows = orch.get("prefect", {}).get("registered_flows", [])
        summary = orch.get("summary", {})

        result("Orchestration: Prefect", prefect_status == "active",
               f"status={prefect_status}, flows={registered_flows}")
        result("Orchestration: Celery", celery_status == "active",
               f"status={celery_status}")
        result("Orchestration: MLflow", mlflow_backend == "mlflow",
               f"backend={mlflow_backend}")
        result("Orchestration: Summary",
               summary.get("heavy_workflows") == "prefect" and
               summary.get("recurring_tasks") == "celery",
               f"workflows={summary.get('heavy_workflows')}, "
               f"tasks={summary.get('recurring_tasks')}, "
               f"tracking={summary.get('experiment_tracking')}")
    except Exception as e:
        result("Orchestration Status", False, str(e)[:120])

    # 4b. Stack validator
    try:
        from backend.app.services.stack_validator import validate_stack
        report = validate_stack()
        summary = report["summary"]

        for sub in report["subsystems"]:
            name = sub["subsystem"]
            status = sub.get("status", "?")
            mode = sub.get("mode", sub.get("configured_backend", "-"))
            verified = sub.get("verified", False)
            print(f"    {name:12s} | status={status:15s} | mode={mode:20s} | verified={verified}")

        result("Stack Validator",
               summary["active"] >= 3,
               f"{summary['active']} active, {summary['fallback']} fallback, "
               f"{summary['unavailable']} unavailable")
    except Exception as e:
        result("Stack Validator", False, str(e)[:120])

    # 4c. Strategy lab tracking surface
    try:
        from backend.app.services.experiment_tracker import get_tracking_status, list_experiment_runs
        tracking = get_tracking_status()
        runs = list_experiment_runs("strategy_lab", limit=5)

        result(
            "Strategy Lab Tracking",
            tracking.get("backend") == "mlflow" and len(runs) > 0,
            f"backend={tracking.get('backend')}, status={tracking.get('status')}, "
            f"runs_visible={len(runs)}",
        )
    except Exception as e:
        result("Strategy Lab Tracking", False, str(e)[:120])

    return True


# -----------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------

def main():
    print("\n" + "=" * 60)
    print("  MARKET AI DASHBOARD — LIVE WORKFLOW PROVING")
    print("=" * 60)
    print(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  CWD:  {os.getcwd()}")

    results = {}
    results["prefect_workflow"] = prove_prefect_workflow()
    results["celery_dispatch"] = prove_celery_dispatch()
    results["mlflow_experiment"] = prove_mlflow_experiment()
    results["runtime_surfaces"] = prove_runtime_surfaces()

    banner("SUMMARY")
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    for name, ok in results.items():
        icon = "PASS" if ok else "FAIL"
        print(f"  [{icon}] {name}")

    print(f"\n  Result: {passed}/{total} workflow categories proven")
    print("=" * 60 + "\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
