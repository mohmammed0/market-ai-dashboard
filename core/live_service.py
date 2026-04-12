from live_market_engine import LiveMarketEngine


def create_live_engine():
    return LiveMarketEngine()


def get_live_quotes_placeholder(symbols):
    return {
        "symbols": [str(symbol).upper() for symbol in symbols or []],
        "status": "not_connected",
        "message": "Live websocket/data adapter is not yet wired into backend routes.",
    }
