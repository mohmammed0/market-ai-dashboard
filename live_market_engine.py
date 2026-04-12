import os
import json
import time
import queue
import asyncio
import threading
import websockets
from yahooquery import Ticker
from app_logger import get_logger

logger = get_logger("live_market_engine")


class LiveMarketEngine:
    def __init__(self, symbols=None, feed="iex", use_test_stream=False, poll_interval=3):
        self.symbols = [s.upper().strip() for s in (symbols or ["AAPL", "MSFT", "NVDA", "SPY"]) if s.strip()]
        self.feed = (feed or "iex").lower()
        self.use_test_stream = bool(use_test_stream)
        self.poll_interval = int(poll_interval)

        self.api_key = os.environ.get("APCA_API_KEY_ID", "").strip()
        self.api_secret = os.environ.get("APCA_API_SECRET_KEY", "").strip()

        self.events = queue.Queue()
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_in_thread, daemon=True)
        self._thread.start()
        logger.info(f"Live engine started | symbols={self.symbols} | mode={'alpaca' if (self.api_key and self.api_secret) else 'polling'}")

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
                await self._stock_stream_loop()
            else:
                await self._polling_loop()
        except Exception as e:
            logger.exception(f"Live engine main loop failed: {e}")
            self._emit("error", {"message": str(e)})

    async def _stock_stream_loop(self):
        if self.use_test_stream:
            url = "wss://stream.data.alpaca.markets/v2/test"
            subscribe_payload = {"action": "subscribe", "trades": ["FAKEPACA"]}
        else:
            url = f"wss://stream.data.alpaca.markets/v2/{self.feed}"
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
                        self._emit("error", item)
                    elif msg_type == "subscription":
                        self._emit("subscription", item)
                    else:
                        self._emit("message", item)

    async def _polling_loop(self):
        logger.info(f"Polling mode active every {self.poll_interval}s | symbols={self.symbols}")
        self._emit("status", {"message": f"polling mode every {self.poll_interval}s"})

        while not self._stop_event.is_set():
            try:
                ticker = Ticker(self.symbols, asynchronous=False)
                price_data = ticker.price

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
                            "source": "yahoo_polling"
                        })
            except Exception as e:
                logger.warning(f"Polling loop error: {e}")
                self._emit("error", {"message": str(e)})

            await asyncio.sleep(self.poll_interval)
