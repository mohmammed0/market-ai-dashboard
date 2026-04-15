#!/usr/bin/env python3
"""
ML Training Worker - السيرفر القديم (5.78.206.88)
يشتغل 24/7 على تدريب نماذج على أسهم أكثر
"""
import os, sys, time, threading, subprocess
from datetime import datetime

sys.path.insert(0, "/opt/market-ai-dashboard/app")

# الأسهم الكبرى للتدريب المستمر
TRAINING_SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "TSLA", "META", "GOOGL", "AMZN",
    "SPY", "QQQ", "AMD", "INTC", "NFLX", "JPM", "BAC", "V",
    "MA", "WMT", "XOM", "CVX", "UNH", "JNJ", "PG", "HD"
]

CYCLE_HOURS = 4  # كل 4 ساعات دورة تدريب كاملة

def log(msg):
    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {msg}", flush=True)

def run_training_cycle():
    log(f"🚀 Starting training cycle on {len(TRAINING_SYMBOLS)} symbols")
    try:
        result = subprocess.run(
            [sys.executable, "train_ml_model.py"],
            cwd="/opt/market-ai-dashboard/app",
            capture_output=True, text=True, timeout=7200,
            env={**os.environ, "MARKET_AI_TRAINING_SYMBOLS": ",".join(TRAINING_SYMBOLS)}
        )
        if result.returncode == 0:
            log("✅ Training cycle completed successfully")
        else:
            log(f"⚠️ Training ended with code {result.returncode}")
            if result.stderr:
                log(f"Stderr: {result.stderr[-500:]}")
    except subprocess.TimeoutExpired:
        log("⏰ Training timeout after 2 hours")
    except Exception as e:
        log(f"❌ Training error: {e}")

def run_breadth_cycle():
    log("📊 Running market breadth analysis...")
    try:
        subprocess.run(
            [sys.executable, "-m", "backend.app.services.breadth_engine"],
            cwd="/opt/market-ai-dashboard/app",
            timeout=600
        )
        log("✅ Breadth analysis done")
    except Exception as e:
        log(f"Breadth error: {e}")

def main():
    log("=" * 50)
    log("ML Worker Server Started (Old Server 5.78.206.88)")
    log(f"Training symbols: {len(TRAINING_SYMBOLS)}")
    log(f"Cycle: every {CYCLE_HOURS} hours")
    log("=" * 50)

    cycle = 0
    while True:
        cycle += 1
        log(f"\n--- Cycle #{cycle} ---")
        run_training_cycle()
        
        # بعد كل 3 دورات، شغّل breadth analysis
        if cycle % 3 == 0:
            run_breadth_cycle()
        
        log(f"😴 Sleeping {CYCLE_HOURS}h until next cycle...")
        time.sleep(CYCLE_HOURS * 3600)

if __name__ == "__main__":
    main()
