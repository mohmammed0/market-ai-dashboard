from __future__ import annotations


class DisabledLiveEngine:
    provider_mode = "unavailable"

    def __init__(self, reason: str | None = None):
        self.reason = str(reason or "Live engine dependencies are unavailable.")
        self.symbols: list[str] = []
        self.poll_interval = 3
        self.api_key = ""
        self.api_secret = ""

    def start(self):
        return None

    def stop(self):
        return None

    def get_event(self, timeout=0.0):
        return None


def create_live_engine():
    try:
        from core.legacy_adapters.live_market import LiveMarketEngine  # noqa: PLC0415
    except Exception as exc:
        return DisabledLiveEngine(reason=str(exc))
    return LiveMarketEngine()


def get_live_quotes_placeholder(symbols):
    return {
        "symbols": [str(symbol).upper() for symbol in symbols or []],
        "status": "not_connected",
        "message": "Live websocket/data adapter is not yet wired into backend routes.",
    }
