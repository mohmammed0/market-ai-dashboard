from __future__ import annotations

from unittest.mock import patch

from backend.app.services import automation_hub
from backend.app.services.automation.common import _rotate_symbol_batch, _select_symbols_for_cycle
from backend.app.services.automation.orchestration import run_automation_job


def test_automation_hub_compatibility_exports():
    assert automation_hub.run_automation_job is run_automation_job


def test_run_automation_job_rejects_unknown_job():
    result = run_automation_job("not-a-real-job", dry_run=True)
    assert result == {"error": "Unsupported automation job: not-a-real-job"}


def test_select_symbols_prefers_local_source_when_available():
    with patch("backend.app.services.automation.common._preferred_local_symbols", return_value=["AAPL", "MSFT", "NVDA"]):
        selected = _select_symbols_for_cycle("SP500", ["TSLA", "META"], desired_count=2)
    assert selected == ["AAPL", "MSFT"]


def test_rotate_symbol_batch_uses_and_updates_runtime_cursor():
    with patch("backend.app.services.runtime_settings.get_runtime_setting_value", return_value=2), patch(
        "backend.app.services.runtime_settings.set_runtime_setting_value"
    ) as set_cursor:
        batch, meta = _rotate_symbol_batch(["AAPL", "MSFT", "NVDA", "TSLA"], desired_count=2)

    assert batch == ["NVDA", "TSLA"]
    assert meta["offset"] == 2
    assert meta["next_offset"] == 0
    set_cursor.assert_called_once_with("auto_trading.rotation_cursor", 0)
