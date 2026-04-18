import os
import json
import time
import queue
import asyncio
import threading
import websockets

try:
    from yahooquery import Ticker as YahooQueryTicker
except Exception:
    YahooQueryTicker = None

try:
    import yfinance as yf
except Exception:
    yf = None

from app_logger import get_logger

logger = get_logger("live_market_engine")


def _safe_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


class LiveMarketEngine:
    def __init__(self, symbols=None, feed="iex", use_test_stream=False, poll_interval=3):
        self.symbols = [s.upper().strip() for s in (symbols or ["AAPL", "MSFT", "NVDA", "SPY"]) if s.strip()]
        self.feed = (feed or "iex").lower()
        self.use_test_stream = bool(use_test_stream)
        self.poll_interval = int(poll_interval)

        self.api_key = (os.environ.get("APCA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY") or "").strip()
        self.api_secret = (os.environ.get("APCA_API_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY") or "").strip()
        self.paper = str(os.environ.get("ALPACA_PAPER", "1")).strip().lower() not in {"0", "false", "no"}
        self.stream_url_override = (
            os.environ.get("MARKET_AI_ALPACA_DATA_STREAM_URL")
            or os.environ.get("ALPACA_DATA_STREAM_URL")
            or ""
        ).strip()
        self.provider_mode = "alpaca_stream" if (self.api_key and self.api_secret) else "polling"

        self.events = queue.Queue()
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_in_thread, daemon=True)
        self._thread.start()
        logger.info(f"Live engine started | symbols={self.symbols} | mode={self.provider_mode}")

    def stop(self):
        self._stop_event.set()
        logger.info("Live engine stop requested")

    def get_event(self, timeout=0.2):
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None

    def _emit(self, event_type, payload):
        self.events.put({
            "type": event_type,
            "payload": payload,
            "ts": time.time(),
        })

    def _run_in_thread(self):
        asyncio.run(self._main())

    async def _main(self):
        try:
            if self.api_key and self.api_secret:
                try:
                    await self._stock_stream_loop()
                    return
                except Exception as e:
                    if self._stop_event.is_set():
                        raise
                    logger.warning(f"Live websocket failed, falling back to polling: {e}")
                    self.provider_mode = "polling"
                    self._emit("status", {"message": "stream fallback to polling", "reason": str(e)})
            await self._polling_loop()
        except Exception as e:
            logger.exception(f"Live engine main loop failed: {e}")
            self._emit("error", {"message": str(e)})

    async def _stock_stream_loop(self):
        if self.use_test_stream:
            url = "wss://stream.data.alpaca.markets/v2/test"
            subscribe_payload = {"action": "subscribe", "trades": ["FAKEPACA"]}
        else:
            default_host = "stream.data.sandbox.alpaca.markets" if self.paper else "stream.data.alpaca.markets"
            url = self.stream_url_override or f"wss://{default_host}/v2/{self.feed}"
            subscribe_payload = {
                "action": "subscribe",
                "trades": self.symbols,
                "quotes": self.symbols,
                "bars": self.symbols,
            }

        logger.info(f"Connecting live websocket: {url}")
        self._emit("status", {"message": f"connecting {url}"})

        async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
            auth_payload = {
                "action": "auth",
                "key": self.api_key,
                "secret": self.api_secret,
            }
            await ws.send(json.dumps(auth_payload))
            await ws.send(json.dumps(subscribe_payload))
            logger.info(f"Live websocket subscribed | symbols={self.symbols}")
            self._emit("status", {"message": "subscribed"})

            while not self._stop_event.is_set():
                raw = await ws.recv()

                try:
                    data = json.loads(raw)
                except Exception:
                    self._emit("raw", {"raw": raw})
                    continue

                if isinstance(data, dict):
                    data = [data]

                for item in data:
                    msg_type = item.get("T")

                    if msg_type == "t":
                        self._emit("trade", item)
                    elif msg_type == "q":
                        self._emit("quote", item)
                    elif msg_type in ("b", "u", "d"):
                        self._emit("bar", item)
                    elif msg_type == "success":
                        self._emit("status", item)
                    elif msg_type == "error":
                        logger.warning(f"Live websocket error event: {item}")
                        message = str(item.get("msg") or item.get("message") or "").strip().lower()
                        if item.get("code") == 401 or "not authenticated" in message or "auth" in message:
                            raise RuntimeError(str(item.get("msg") or item.get("message") or "stream authentication failed"))
                        self._emit("error", item)
                    elif msg_type == "subscription":
                        self._emit("subscription", item)
                    else:
                        self._emit("message", item)

    def _polling_source(self):
        if YahooQueryTicker is not None:
            return "yahooquery"
        if yf is not None:
            return "yfinance"
        return None

    def _fetch_price_data(self):
        if YahooQueryTicker is not None:
            ticker = YahooQueryTicker(self.symbols, asynchronous=False)
            return ticker.price if isinstance(ticker.price, dict) else {}

        if yf is None:
            raise RuntimeError("Neither yahooquery nor yfinance is installed for polling mode.")

        payload = {}
        for symbol in self.symbols:
            ticker = yf.Ticker(symbol)
            fast_info = {}
            try:
                fast_info = dict(getattr(ticker, "fast_info", {}) or {})
            except Exception:
                fast_info = {}

            history = None
            try:
                history = ticker.history(period="5d", interval="1d", auto_adjust=False, prepost=True)
            except Exception:
                history = None

            previous_close = _safe_float(fast_info.get("previousClose"))
            if previous_close in (None, 0.0) and history is not None and not history.empty and len(history.index) >= 2:
                try:
                    previous_close = _safe_float(history["Close"].dropna().iloc[-2])
                except Exception:
                    previous_close = previous_close

            current_price = _safe_float(
                fast_info.get("lastPrice")
                or fast_info.get("regularMarketPrice")
                or fast_info.get("last_price")
            )
            if current_price is None and history is not None and not history.empty:
                try:
                    current_price = _safe_float(history["Close"].dropna().iloc[-1])
                except Exception:
                    current_price = None

            payload[symbol] = {
                "regularMarketPrice": current_price,
                "regularMarketPreviousClose": previous_close,
                "regularMarketDayHigh": _safe_float(fast_info.get("dayHigh") or fast_info.get("regularMarketDayHigh")),
                "regularMarketDayLow": _safe_float(fast_info.get("dayLow") or fast_info.get("regularMarketDayLow")),
                "regularMarketVolume": _safe_float(fast_info.get("lastVolume") or fast_info.get("regularMarketVolume")),
            }
        return payload

    async def _polling_loop(self):
        polling_source = self._polling_source()
        if polling_source is None:
            raise RuntimeError("Polling mode requires yahooquery or yfinance to be installed.")

        logger.info(f"Polling mode active every {self.poll_interval}s | symbols={self.symbols} | source={polling_source}")
        self._emit("status", {"message": f"polling mode every {self.poll_interval}s", "source": polling_source})

        while not self._stop_event.is_set():
            try:
                price_data = self._fetch_price_data()

                if isinstance(price_data, dict):
                    for symbol in self.symbols:
                        item = price_data.get(symbol, {})
                        if not isinstance(item, dict):
                            continue

                        current_price = item.get("regularMarketPrice")
                        prev_close = item.get("regularMarketPreviousClose")
                        day_high = item.get("regularMarketDayHigh")
                        day_low = item.get("regularMarketDayLow")
                        volume = item.get("regularMarketVolume")
                        change = None
                        change_pct = None

                        if current_price is not None and prev_close not in (None, 0):
                            change = current_price - prev_close
                            change_pct = (change / prev_close) * 100

                        self._emit("quote", {
                            "symbol": symbol,
                            "price": current_price,
                            "prev_close": prev_close,
                            "change": change,
                            "change_pct": change_pct,
                            "day_high": day_high,
                            "day_low": day_low,
                            "volume": volume,
                            "source": f"{polling_source}_polling",
                        })
            except Exception as e:
                logger.warning(f"Polling loop error: {e}")
                self._emit("error", {"message": str(e)})

            await asyncio.sleep(self.poll_interval)
