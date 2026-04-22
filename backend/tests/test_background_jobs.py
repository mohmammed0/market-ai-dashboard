from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.orm import close_all_sessions


_TMP_DIR = tempfile.TemporaryDirectory(prefix="market_ai_jobs_tests_")
_DB_PATH = Path(_TMP_DIR.name) / "jobs_test.db"

os.environ["MARKET_AI_DATABASE_URL"] = f"sqlite:///{_DB_PATH.as_posix()}"
os.environ["MARKET_AI_ENABLE_SCHEDULER"] = "0"
os.environ["MARKET_AI_ENABLE_CONTINUOUS_LEARNING"] = "0"
os.environ["MARKET_AI_AUTH_ENABLED"] = "0"

from fastapi.testclient import TestClient

import backend.app.services.background_jobs as background_jobs_module
from backend.app.db.session import engine
from backend.app.main import app
from backend.app.services.background_jobs import (
    JOB_TYPE_SCAN,
    get_background_job,
    run_background_job,
    submit_background_job,
)


class BackgroundJobsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.auth_enabled_patcher = patch("backend.app.api.routes.auth.AUTH_ENABLED", False)
        cls.warmup_patcher = patch("backend.app.bootstrap.runtime._warm_runtime_caches", return_value=None)
        cls.auth_enabled_patcher.start()
        cls.warmup_patcher.start()
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_cm.__exit__(None, None, None)
        close_all_sessions()
        engine.dispose()
        cls.warmup_patcher.stop()
        cls.auth_enabled_patcher.stop()
        _TMP_DIR.cleanup()

    def test_backtest_endpoint_returns_job_id_and_status(self):
        with patch("backend.app.services.background_jobs._spawn_background_job_process", return_value=999):
            response = self.client.post(
                "/api/backtest",
                json={
                    "instrument": "AAPL",
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31",
                    "hold_days": 5,
                    "min_technical_score": 2,
                    "buy_score_threshold": 3,
                    "sell_score_threshold": 4,
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload.get("job_id"))
        self.assertEqual(payload.get("type"), "backtest_classic")
        self.assertIn(payload.get("status"), {"pending", "running"})

        status_response = self.client.get(f"/api/jobs/{payload['job_id']}")
        self.assertEqual(status_response.status_code, 200, status_response.text)
        status_payload = status_response.json()
        self.assertEqual(status_payload["job_id"], payload["job_id"])
        self.assertEqual(status_payload["type"], "backtest_classic")

    def test_background_job_can_complete_and_persist_result(self):
        with patch("backend.app.services.background_jobs._spawn_background_job_process", return_value=321), patch(
            "backend.app.services.background_jobs.is_process_running", return_value=True
        ):
            created = submit_background_job(
                job_type=JOB_TYPE_SCAN,
                payload={
                    "symbols": ["AAPL", "MSFT"],
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31",
                },
                requested_by="tester",
            )
            duplicate = submit_background_job(
                job_type=JOB_TYPE_SCAN,
                payload={
                    "symbols": ["AAPL", "MSFT"],
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31",
                },
                requested_by="tester",
            )

        self.assertEqual(created["job_id"], duplicate["job_id"])
        self.assertTrue(duplicate["deduplicated"])

        fake_result = {
            "items": [
                {"instrument": "AAPL", "signal": "BUY"},
                {"instrument": "MSFT", "signal": "HOLD"},
            ],
            "summary": {"top_pick": "AAPL"},
        }
        with patch.dict(background_jobs_module.JOB_EXECUTORS, {JOB_TYPE_SCAN: lambda payload: fake_result}, clear=False), patch(
            "backend.app.services.background_jobs.is_process_running", return_value=True
        ):
            exit_code = run_background_job(created["job_id"])

        self.assertEqual(exit_code, 0)
        stored = get_background_job(created["job_id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored["status"], "completed")
        self.assertEqual(stored["progress"], 100)
        self.assertEqual(stored["result"]["summary"]["top_pick"], "AAPL")
        self.assertEqual(stored["result_summary"]["top_pick"], "AAPL")


if __name__ == "__main__":
    unittest.main()
