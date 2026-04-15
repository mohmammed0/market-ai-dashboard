"""
Worker API - السيرفر القديم كـ Compute Worker
يستقبل مهام ثقيلة من السيرفر الجديد
"""
import os, sys, time, subprocess, threading, uuid
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Worker API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

WORKER_SECRET = os.getenv("WORKER_SECRET", "worker-secret-2026")
tasks: dict = {}

def check_secret(secret):
    if secret != WORKER_SECRET:
        raise HTTPException(status_code=403, detail="Invalid worker secret")

@app.get("/worker/health")
def health():
    running = sum(1 for t in tasks.values() if t["status"] == "running")
    try:
        load = open("/proc/loadavg").read().split()[0]
        with open("/proc/meminfo") as f:
            mem = {l.split()[0]: int(l.split()[1]) for l in f if l.startswith(("MemTotal","MemAvailable"))}
        mem_pct = round((1 - mem["MemAvailable:"] / mem["MemTotal:"]) * 100)
    except Exception:
        load, mem_pct = "?", 0
    return {
        "status": "ok", "server": "worker-old",
        "ip": "5.78.206.88",
        "tasks_running": running,
        "tasks_total": len(tasks),
        "system": {"load_1m": load, "mem_used_pct": mem_pct},
        "ts": datetime.utcnow().isoformat(),
    }

class BacktestRequest(BaseModel):
    symbol: str
    strategy: str = "ensemble_policy"
    start_date: str = "2023-01-01"
    params: dict = {}

@app.post("/worker/backtest")
def submit_backtest(req: BacktestRequest, x_worker_secret: str = Header(None)):
    check_secret(x_worker_secret)
    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {"id": task_id, "type": "backtest", "symbol": req.symbol,
                      "status": "queued", "submitted_at": datetime.utcnow().isoformat(),
                      "result": None, "error": None}
    def run():
        tasks[task_id]["status"] = "running"
        try:
            cmd = [sys.executable, "-m", "backend.app.services.backtest_runner",
                   "--symbol", req.symbol, "--strategy", req.strategy]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                                  cwd="/opt/market-ai-dashboard/app")
            tasks[task_id]["status"] = "done" if proc.returncode == 0 else "failed"
            tasks[task_id]["result"] = proc.stdout[-3000:]
            tasks[task_id]["error"] = proc.stderr[-500:] if proc.returncode != 0 else None
        except Exception as e:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["error"] = str(e)
        tasks[task_id]["finished_at"] = datetime.utcnow().isoformat()
    threading.Thread(target=run, daemon=True).start()
    return {"task_id": task_id, "status": "queued"}

class TrainRequest(BaseModel):
    symbols: list = ["AAPL", "MSFT", "NVDA", "SPY"]

@app.post("/worker/train")
def submit_training(req: TrainRequest, x_worker_secret: str = Header(None)):
    check_secret(x_worker_secret)
    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {"id": task_id, "type": "ml_train", "symbols": req.symbols,
                      "status": "queued", "submitted_at": datetime.utcnow().isoformat(),
                      "result": None, "error": None}
    def run():
        tasks[task_id]["status"] = "running"
        try:
            cmd = [sys.executable, "train_ml_model.py"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                  cwd="/opt/market-ai-dashboard/app")
            tasks[task_id]["status"] = "done" if proc.returncode == 0 else "failed"
            tasks[task_id]["result"] = proc.stdout[-3000:]
        except Exception as e:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["error"] = str(e)
        tasks[task_id]["finished_at"] = datetime.utcnow().isoformat()
    threading.Thread(target=run, daemon=True).start()
    return {"task_id": task_id, "status": "queued"}

@app.get("/worker/tasks")
def list_tasks(x_worker_secret: str = Header(None)):
    check_secret(x_worker_secret)
    return {"tasks": list(reversed(list(tasks.values())))[:20]}

@app.get("/worker/tasks/{task_id}")
def get_task(task_id: str, x_worker_secret: str = Header(None)):
    check_secret(x_worker_secret)
    if task_id not in tasks:
        raise HTTPException(404, "Task not found")
    return tasks[task_id]

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, workers=1)
