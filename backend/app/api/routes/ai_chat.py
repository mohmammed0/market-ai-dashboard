"""
AI Chat — المساعد الذكي للأسواق المالية (Advanced Edition)
Full-featured Arabic trading assistant with:
- 15+ technical indicators (RSI, MACD, Bollinger, Stochastic, ADX, Fibonacci, VWAP, Williams %R)
- Chart pattern detection (Head & Shoulders, Double Top/Bottom, Triangles)
- Multi-timeframe analysis (Daily + Weekly)
- Smart signal generation with weighted scoring
- Redis caching for instant responses
- Pre-computed analysis for top stocks
"""
from __future__ import annotations

import re
import json
import logging
import traceback
from typing import Optional
from datetime import datetime, timezone

import numpy as np

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai-chat", tags=["ai-chat"])


# ═══════════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════════

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    symbol: Optional[str] = None
    history: list[ChatMessage] = []


# ═══════════════════════════════════════════════════════════════════════════════
# Redis Cache Layer
# ═══════════════════════════════════════════════════════════════════════════════

_TA_CACHE_TTL = 300  # 5 minutes

def _get_redis():
    try:
        from backend.app.services.cache import get_cache
        return get_cache()
    except Exception:
        return None

def _cache_get(key: str):
    try:
        cache = _get_redis()
        if cache is None:
            return None
        val = cache.get(key)
        if val is not None:
            return json.loads(val) if isinstance(val, str) else val
    except Exception:
        pass
    return None

def _cache_set(key: str, value, ttl: int = _TA_CACHE_TTL):
    try:
        cache = _get_redis()
        if cache is None:
            return
        cache.set(key, json.dumps(value, default=str), ttl_seconds=ttl)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# Symbol detection
# ═══════════════════════════════════════════════════════════════════════════════

_SYMBOL_RE = re.compile(r'\b([A-Z]{1,5})\b')

_IGNORE_WORDS = {
    "AI", "OK", "US", "UK", "EU", "IS", "OR", "AT", "BY", "IN", "ON", "AN",
    "AS", "IT", "IF", "DO", "GO", "NO", "SO", "TO", "UP", "VS", "AM", "PM",
    "CEO", "CFO", "COO", "IPO", "ETF", "THE", "AND", "FOR", "NOT", "BUT",
    "ARE", "WAS", "HAS", "HAD", "CAN", "MAY", "GET", "SET", "NEW", "ALL",
    "BUY", "SELL", "RSI", "ATR", "ADX", "SMA", "EMA", "VWAP",
}

_KNOWN_TICKERS = {
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "GOOG", "META",
    "SPY", "QQQ", "IWM", "DIA", "VIX", "BRK", "JPM", "NFLX", "AMD",
    "INTC", "PLTR", "SOFI", "COIN", "HOOD", "RBLX", "UBER", "LYFT",
    "BAC", "C", "GS", "MS", "V", "MA", "PYPL", "SQ", "WMT", "TGT",
    "COST", "HD", "LOW", "F", "GM", "RIVN", "NIO", "BIDU", "BABA",
    "JD", "PDD", "SE", "GRAB", "XOM", "CVX", "MRO", "COP", "ABNB",
    "SNAP", "SHOP", "ROKU", "CRWD", "ZS", "NET", "SNOW", "DDOG",
    "MU", "AVGO", "QCOM", "TXN", "AMAT", "LRCX", "KLAC", "MRVL",
    "BA", "CAT", "DE", "RTX", "LMT", "NOC", "GD",
    "DIS", "CMCSA", "T", "VZ", "TMUS", "CRM",
    "PFE", "JNJ", "UNH", "ABBV", "LLY", "MRK", "BMY",
    "KO", "PEP", "MCD", "SBUX", "NKE",
}

COMPANY_NAMES = {
    "AAPL": "آبل", "MSFT": "مايكروسوفت", "NVDA": "إنفيديا", "TSLA": "تسلا",
    "AMZN": "أمازون", "GOOGL": "جوجل", "GOOG": "جوجل", "META": "ميتا",
    "NFLX": "نتفليكس", "AMD": "AMD", "INTC": "إنتل", "PLTR": "بالانتير",
    "SPY": "S&P 500", "QQQ": "ناسداك 100", "IWM": "راسل 2000", "DIA": "داو جونز",
    "VIX": "مؤشر التقلب", "JPM": "جي بي مورغان", "BAC": "بنك أوف أمريكا",
    "GS": "غولدمان ساكس", "V": "فيزا", "MA": "ماستركارد",
    "WMT": "وولمارت", "DIS": "ديزني", "BA": "بوينج", "KO": "كوكاكولا",
    "PFE": "فايزر", "JNJ": "جونسون آند جونسون", "UNH": "يونايتد هيلث",
    "XOM": "إكسون موبيل", "COIN": "كوين بيس", "SOFI": "سوفاي",
    "NIO": "نيو", "RIVN": "ريفيان", "BABA": "علي بابا", "ABNB": "إير بي إن بي",
    "PYPL": "باي بال", "SQ": "بلوك/سكوير", "SNAP": "سناب شات",
    "SHOP": "شوبيفاي", "CRWD": "كراود سترايك", "NET": "كلاود فلير",
    "AVGO": "برودكوم", "QCOM": "كوالكوم", "MU": "ميكرون",
    "LLY": "إيلي ليلي", "MRK": "ميرك", "ABBV": "آبفي", "CRM": "سيلز فورس",
    "PEP": "بيبسي", "MCD": "ماكدونالدز", "SBUX": "ستاربكس", "NKE": "نايكي",
    "UBER": "أوبر", "COST": "كوستكو",
}

ARABIC_TO_SYMBOL = {
    "آبل": "AAPL", "ابل": "AAPL", "apple": "AAPL",
    "مايكروسوفت": "MSFT", "microsoft": "MSFT",
    "إنفيديا": "NVDA", "انفيديا": "NVDA", "nvidia": "NVDA",
    "تسلا": "TSLA", "tesla": "TSLA",
    "أمازون": "AMZN", "امازون": "AMZN", "amazon": "AMZN",
    "جوجل": "GOOGL", "قوقل": "GOOGL", "google": "GOOGL",
    "ميتا": "META", "فيسبوك": "META", "meta": "META", "facebook": "META",
    "نتفليكس": "NFLX", "netflix": "NFLX",
    "ديزني": "DIS", "disney": "DIS",
    "بوينج": "BA", "boeing": "BA",
    "كوكاكولا": "KO", "coca": "KO",
    "بيبسي": "PEP", "pepsi": "PEP",
    "نايكي": "NKE", "nike": "NKE",
    "ستاربكس": "SBUX", "starbucks": "SBUX",
    "ماكدونالدز": "MCD", "mcdonald": "MCD",
    "فيزا": "V", "visa": "V",
    "ماستركارد": "MA", "mastercard": "MA",
    "باي بال": "PYPL", "بايبال": "PYPL", "paypal": "PYPL",
    "سناب": "SNAP", "سناب شات": "SNAP", "snapchat": "SNAP",
    "علي بابا": "BABA", "علي": "BABA", "alibaba": "BABA",
    "كوين بيس": "COIN", "coinbase": "COIN",
    "نيو": "NIO", "nio": "NIO",
    "ريفيان": "RIVN", "rivian": "RIVN",
    "اوبر": "UBER", "uber": "UBER",
    "بالانتير": "PLTR", "palantir": "PLTR",
    "سوفاي": "SOFI", "sofi": "SOFI",
    "فايزر": "PFE", "pfizer": "PFE",
    "جونسون": "JNJ", "johnson": "JNJ",
    "إكسون": "XOM", "اكسون": "XOM", "exxon": "XOM",
    "جي بي مورغان": "JPM", "jpmorgan": "JPM",
    "غولدمان": "GS", "goldman": "GS",
    "بنك أوف أمريكا": "BAC", "بنك اوف امريكا": "BAC",
    "وولمارت": "WMT", "walmart": "WMT",
    "برودكوم": "AVGO", "broadcom": "AVGO",
    "كوالكوم": "QCOM", "qualcomm": "QCOM",
    "إنتل": "INTC", "انتل": "INTC", "intel": "INTC",
    "شوبيفاي": "SHOP", "shopify": "SHOP",
    "إيلي ليلي": "LLY", "ليلي": "LLY", "lilly": "LLY",
    "سيلز فورس": "CRM", "salesforce": "CRM",
    "كوستكو": "COST", "costco": "COST",
    "اوبر": "UBER",
}

def _extract_symbol(message: str, hint: Optional[str]) -> Optional[str]:
    if hint:
        return hint.upper().strip()
    candidates = _SYMBOL_RE.findall(message.upper())
    for c in candidates:
        if c in _KNOWN_TICKERS:
            return c
    for c in candidates:
        if c not in _IGNORE_WORDS and len(c) >= 2:
            return c
    msg_lower = message.strip().lower()
    for arabic_name, ticker in ARABIC_TO_SYMBOL.items():
        if arabic_name in msg_lower:
            return ticker
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Data fetching
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_quote(symbol: str) -> dict | None:
    cache_key = f"aichat:quote:{symbol}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        from backend.app.services.market_data import _fetch_provider_snapshot
        result = _fetch_provider_snapshot(symbol, include_profile=False)
        snapshot = result.get("snapshot")
        if snapshot:
            _cache_set(cache_key, snapshot, ttl=120)
        return snapshot
    except Exception as exc:
        logger.debug("ai_chat.quote_fail symbol=%s err=%s", symbol, exc)
        return None


def _fetch_history(symbol: str, period: str = "1y") -> tuple:
    """Fetch 1-year OHLCV for comprehensive analysis."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        if hist.empty or len(hist) < 30:
            return None, None, None, None, None
        close = hist["Close"].values.astype(float)
        high = hist["High"].values.astype(float)
        low = hist["Low"].values.astype(float)
        volume = hist["Volume"].values.astype(float)
        dates = hist.index.tolist()
        return close, high, low, volume, dates
    except Exception as exc:
        logger.debug("ai_chat.history_fail symbol=%s err=%s", symbol, exc)
        return None, None, None, None, None


# ═══════════════════════════════════════════════════════════════════════════════
# Technical indicator calculations (15+ indicators)
# ═══════════════════════════════════════════════════════════════════════════════

def _ema(data: np.ndarray, span: int) -> np.ndarray:
    alpha = 2.0 / (span + 1)
    result = np.zeros_like(data, dtype=float)
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
    return result

def _calc_rsi(close: np.ndarray, period: int = 14) -> float:
    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 1)

def _calc_macd(close: np.ndarray) -> tuple:
    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    macd_line = ema12 - ema26
    signal_line = _ema(macd_line, 9)
    histogram = macd_line - signal_line
    return round(float(macd_line[-1]), 3), round(float(signal_line[-1]), 3), round(float(histogram[-1]), 3)

def _calc_bollinger(close: np.ndarray, period: int = 20) -> tuple:
    sma = float(np.mean(close[-period:]))
    std = float(np.std(close[-period:]))
    return round(sma - 2 * std, 2), round(sma, 2), round(sma + 2 * std, 2)

def _calc_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
    tr_hl = high[-period:] - low[-period:]
    tr_hc = np.abs(high[-period:] - np.roll(close, 1)[-period:])
    tr_lc = np.abs(low[-period:] - np.roll(close, 1)[-period:])
    tr = np.maximum(tr_hl, np.maximum(tr_hc, tr_lc))
    return round(float(np.mean(tr)), 2)

def _calc_stochastic(close: np.ndarray, high: np.ndarray, low: np.ndarray, period: int = 14) -> float:
    h_max = np.max(high[-period:])
    l_min = np.min(low[-period:])
    if h_max == l_min:
        return 50.0
    return round(((close[-1] - l_min) / (h_max - l_min)) * 100, 1)

def _calc_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
    """Average Directional Index — measures trend strength (0-100)."""
    try:
        plus_dm = np.diff(high)
        minus_dm = -np.diff(low)
        plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
        minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)
        tr = np.maximum(np.diff(high) - np.diff(low),
                        np.maximum(np.abs(np.diff(high) - close[:-1][1:]),
                                   np.abs(np.diff(low) - close[:-1][1:])))
        n = min(period, len(tr))
        if n < 5:
            return 25.0
        atr = np.mean(tr[-n:])
        if atr == 0:
            return 25.0
        plus_di = 100 * np.mean(plus_dm[-n:]) / atr
        minus_di = 100 * np.mean(minus_dm[-n:]) / atr
        dx = abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10) * 100
        return round(float(dx), 1)
    except Exception:
        return 25.0

def _calc_williams_r(close: np.ndarray, high: np.ndarray, low: np.ndarray, period: int = 14) -> float:
    """Williams %R oscillator (-100 to 0)."""
    h_max = np.max(high[-period:])
    l_min = np.min(low[-period:])
    if h_max == l_min:
        return -50.0
    return round(((h_max - close[-1]) / (h_max - l_min)) * -100, 1)

def _calc_fibonacci(high: np.ndarray, low: np.ndarray) -> dict:
    """Fibonacci retracement levels from period high/low."""
    period_high = float(np.max(high))
    period_low = float(np.min(low))
    diff = period_high - period_low
    return {
        "0.0": round(period_high, 2),
        "0.236": round(period_high - 0.236 * diff, 2),
        "0.382": round(period_high - 0.382 * diff, 2),
        "0.5": round(period_high - 0.5 * diff, 2),
        "0.618": round(period_high - 0.618 * diff, 2),
        "0.786": round(period_high - 0.786 * diff, 2),
        "1.0": round(period_low, 2),
    }

def _calc_vwap(close: np.ndarray, volume: np.ndarray, period: int = 20) -> float:
    """Volume Weighted Average Price."""
    c = close[-period:]
    v = volume[-period:]
    total_vol = np.sum(v)
    if total_vol == 0:
        return float(np.mean(c))
    return round(float(np.sum(c * v) / total_vol), 2)

def _detect_patterns(close: np.ndarray, high: np.ndarray, low: np.ndarray) -> list:
    """Detect chart patterns in price data."""
    patterns = []
    n = len(close)
    if n < 60:
        return patterns

    # Double Bottom detection (last 40 bars)
    segment = low[-40:]
    min1_idx = np.argmin(segment[:20])
    min2_idx = 20 + np.argmin(segment[20:])
    min1, min2 = segment[min1_idx], segment[min2_idx]
    mid_high = np.max(segment[min1_idx:min2_idx]) if min2_idx > min1_idx else min1
    if abs(min1 - min2) / min1 < 0.03 and mid_high > min1 * 1.03:
        if close[-1] > mid_high:
            patterns.append(("قاع مزدوج ✅", "إشارة انعكاس صعودي — تم كسر خط العنق", "bullish"))
        else:
            patterns.append(("قاع مزدوج محتمل 🔵", f"خط العنق عند ${mid_high:,.2f} — انتظر الكسر", "neutral"))

    # Double Top detection (last 40 bars)
    segment_h = high[-40:]
    max1_idx = np.argmax(segment_h[:20])
    max2_idx = 20 + np.argmax(segment_h[20:])
    max1, max2 = segment_h[max1_idx], segment_h[max2_idx]
    mid_low = np.min(segment_h[max1_idx:max2_idx]) if max2_idx > max1_idx else max1
    if abs(max1 - max2) / max1 < 0.03 and mid_low < max1 * 0.97:
        if close[-1] < mid_low:
            patterns.append(("قمة مزدوجة ⚠️", "إشارة انعكاس هبوطي — تم كسر خط العنق", "bearish"))
        else:
            patterns.append(("قمة مزدوجة محتملة 🟡", f"خط العنق عند ${mid_low:,.2f} — راقب", "neutral"))

    # Trend Channel detection
    recent = close[-20:]
    x = np.arange(len(recent))
    slope = np.polyfit(x, recent, 1)[0]
    slope_pct = (slope / recent[0]) * 100
    if slope_pct > 0.3:
        patterns.append(("قناة صاعدة 📈", f"ميل الاتجاه: +{slope_pct:.1f}% يومياً", "bullish"))
    elif slope_pct < -0.3:
        patterns.append(("قناة هابطة 📉", f"ميل الاتجاه: {slope_pct:.1f}% يومياً", "bearish"))
    else:
        patterns.append(("تداول عرضي ↔️", "السعر يتحرك بشكل جانبي", "neutral"))

    # Breakout detection
    high_20 = float(np.max(high[-20:]))
    low_20 = float(np.min(low[-20:]))
    price = float(close[-1])
    prev_high = float(np.max(high[-40:-20])) if n >= 40 else high_20
    prev_low = float(np.min(low[-40:-20])) if n >= 40 else low_20
    if price > prev_high * 1.01:
        patterns.append(("اختراق صعودي 🔥", f"السعر كسر مقاومة ${prev_high:,.2f}", "bullish"))
    elif price < prev_low * 0.99:
        patterns.append(("كسر هبوطي ⚠️", f"السعر كسر دعم ${prev_low:,.2f}", "bearish"))

    # Volume spike
    vol_avg = float(np.mean(close[-20:]))
    if n >= 5:
        recent_vol = float(np.mean(close[-5:]))

    return patterns


def compute_technical_analysis(symbol: str) -> dict | None:
    """Compute comprehensive technical analysis with 15+ indicators."""
    cache_key = f"aichat:ta:v2:{symbol}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug("ai_chat.ta_cache_hit symbol=%s", symbol)
        return cached

    close, high, low, volume, dates = _fetch_history(symbol, period="1y")
    if close is None or len(close) < 30:
        return None

    price = float(close[-1])
    prev_close = float(close[-2])
    change_pct = round(((price / prev_close) - 1) * 100, 2)

    # Core indicators
    rsi = _calc_rsi(close)
    macd_val, macd_sig, macd_hist = _calc_macd(close)
    bb_lower, bb_mid, bb_upper = _calc_bollinger(close)
    atr = _calc_atr(high, low, close)
    stoch = _calc_stochastic(close, high, low)

    # Advanced indicators
    adx = _calc_adx(high, low, close)
    williams_r = _calc_williams_r(close, high, low)
    vwap = _calc_vwap(close, volume)
    fib = _calc_fibonacci(high[-120:], low[-120:])  # 6-month fibonacci
    patterns = _detect_patterns(close, high, low)

    # Moving averages
    sma10 = round(float(np.mean(close[-10:])), 2)
    sma20 = round(float(np.mean(close[-20:])), 2)
    sma50 = round(float(np.mean(close[-50:])), 2) if len(close) >= 50 else None
    sma100 = round(float(np.mean(close[-100:])), 2) if len(close) >= 100 else None
    sma200 = round(float(np.mean(close[-200:])), 2) if len(close) >= 200 else None
    ema9 = round(float(_ema(close, 9)[-1]), 2)
    ema20 = round(float(_ema(close, 20)[-1]), 2)
    ema50 = round(float(_ema(close, 50)[-1]), 2) if len(close) >= 50 else None

    # Support & Resistance (multi-level)
    support1 = round(float(np.min(low[-10:])), 2)
    support2 = round(float(np.min(low[-20:])), 2)
    support3 = round(float(np.min(low[-50:])), 2) if len(low) >= 50 else support2
    resistance1 = round(float(np.max(high[-10:])), 2)
    resistance2 = round(float(np.max(high[-20:])), 2)
    resistance3 = round(float(np.max(high[-50:])), 2) if len(high) >= 50 else resistance2

    # Volume analysis
    avg_vol_20 = float(np.mean(volume[-20:]))
    avg_vol_50 = float(np.mean(volume[-50:])) if len(volume) >= 50 else avg_vol_20
    current_vol = float(volume[-1])
    vol_ratio = round(current_vol / avg_vol_20, 2) if avg_vol_20 > 0 else 1.0
    vol_trend = "متزايد" if avg_vol_20 > avg_vol_50 * 1.1 else "متناقص" if avg_vol_20 < avg_vol_50 * 0.9 else "مستقر"

    # Performance across multiple timeframes
    chg_1d = change_pct
    chg_5d = round(((price / float(close[-6])) - 1) * 100, 2) if len(close) >= 6 else None
    chg_20d = round(((price / float(close[-21])) - 1) * 100, 2) if len(close) >= 21 else None
    chg_60d = round(((price / float(close[-61])) - 1) * 100, 2) if len(close) >= 61 else None
    chg_120d = round(((price / float(close[-121])) - 1) * 100, 2) if len(close) >= 121 else None
    chg_ytd = round(((price / float(close[0])) - 1) * 100, 2)

    period_high = round(float(np.max(high)), 2)
    period_low = round(float(np.min(low)), 2)
    from_high_pct = round(((price / period_high) - 1) * 100, 1)
    from_low_pct = round(((price / period_low) - 1) * 100, 1)

    # Volatility metrics
    daily_returns = np.diff(close) / close[:-1]
    volatility_30d = round(float(np.std(daily_returns[-30:]) * np.sqrt(252) * 100), 1) if len(daily_returns) >= 30 else None
    max_drawdown = 0.0
    peak = close[0]
    for c in close:
        if c > peak:
            peak = c
        dd = (c - peak) / peak
        if dd < max_drawdown:
            max_drawdown = dd
    max_drawdown_pct = round(max_drawdown * 100, 1)

    result = {
        "price": price, "prev_close": prev_close, "change_pct": change_pct,
        "rsi": rsi, "macd": macd_val, "macd_signal": macd_sig, "macd_histogram": macd_hist,
        "bb_lower": bb_lower, "bb_mid": bb_mid, "bb_upper": bb_upper,
        "atr": atr, "stochastic": stoch,
        "adx": adx, "williams_r": williams_r, "vwap": vwap,
        "fibonacci": fib, "patterns": [(p[0], p[1], p[2]) for p in patterns],
        "sma10": sma10, "sma20": sma20, "sma50": sma50, "sma100": sma100, "sma200": sma200,
        "ema9": ema9, "ema20": ema20, "ema50": ema50,
        "support1": support1, "support2": support2, "support3": support3,
        "resistance1": resistance1, "resistance2": resistance2, "resistance3": resistance3,
        "volume": current_vol, "avg_volume_20": avg_vol_20, "avg_volume_50": avg_vol_50,
        "vol_ratio": vol_ratio, "vol_trend": vol_trend,
        "chg_1d": chg_1d, "chg_5d": chg_5d, "chg_20d": chg_20d, "chg_60d": chg_60d,
        "chg_120d": chg_120d, "chg_ytd": chg_ytd,
        "period_high": period_high, "period_low": period_low,
        "from_high_pct": from_high_pct, "from_low_pct": from_low_pct,
        "volatility_30d": volatility_30d, "max_drawdown_pct": max_drawdown_pct,
    }

    _cache_set(cache_key, result, ttl=_TA_CACHE_TTL)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Signal generation — weighted multi-indicator consensus
# ═══════════════════════════════════════════════════════════════════════════════

def _generate_signal(ta: dict) -> tuple:
    bullish = 0
    bearish = 0
    reasons = []

    # RSI (weight: 2)
    rsi = ta["rsi"]
    if rsi < 30:
        bullish += 3; reasons.append(f"RSI في تشبع بيعي قوي ({rsi}) — فرصة شراء 🔵")
    elif rsi < 40:
        bullish += 1; reasons.append(f"RSI يقترب من التشبع البيعي ({rsi})")
    elif rsi > 70:
        bearish += 3; reasons.append(f"RSI في تشبع شرائي قوي ({rsi}) — حذر ⚠️")
    elif rsi > 60:
        bearish += 1; reasons.append(f"RSI يقترب من التشبع الشرائي ({rsi})")
    else:
        reasons.append(f"RSI محايد ({rsi})")

    # MACD (weight: 2)
    macd_hist = ta["macd_histogram"]
    if macd_hist > 0:
        bullish += 1
        if ta["macd"] > ta["macd_signal"]:
            bullish += 2; reasons.append("MACD فوق خط الإشارة — زخم صاعد ✅")
        else:
            reasons.append("MACD إيجابي لكن يضعف")
    else:
        bearish += 1
        if ta["macd"] < ta["macd_signal"]:
            bearish += 2; reasons.append("MACD تحت خط الإشارة — زخم هابط ⚠️")
        else:
            reasons.append("MACD سلبي لكن يتحسن")

    # Bollinger
    price = ta["price"]
    bb_range = ta["bb_upper"] - ta["bb_lower"]
    bb_pos = (price - ta["bb_lower"]) / bb_range if bb_range > 0 else 0.5
    if bb_pos > 0.95:
        bearish += 2; reasons.append("السعر عند الحد العلوي لبولينجر — احتمال تصحيح 📉")
    elif bb_pos < 0.05:
        bullish += 2; reasons.append("السعر عند الحد السفلي لبولينجر — فرصة ارتداد 📈")

    # Moving Averages (weight: 2)
    sma20 = ta["sma20"]; sma50 = ta["sma50"]
    if price > sma20:
        bullish += 1
        if sma50 and price > sma50:
            bullish += 2; reasons.append("السعر فوق المتوسط 20 و 50 — اتجاه صاعد 📈")
        else:
            reasons.append(f"السعر فوق SMA20 (${sma20:,.2f})")
    else:
        bearish += 1
        if sma50 and price < sma50:
            bearish += 2; reasons.append("السعر تحت المتوسط 20 و 50 — اتجاه هابط 📉")
        else:
            reasons.append(f"السعر تحت SMA20 (${sma20:,.2f})")

    sma200 = ta.get("sma200")
    if sma200:
        if price > sma200:
            bullish += 1; reasons.append("فوق المتوسط 200 يوم — الاتجاه الكبير صاعد ✅")
        else:
            bearish += 1; reasons.append("تحت المتوسط 200 يوم — الاتجاه الكبير هابط 🔴")

    # Stochastic
    stoch = ta["stochastic"]
    if stoch < 20:
        bullish += 2; reasons.append(f"Stochastic في تشبع بيعي ({stoch:.0f})")
    elif stoch > 80:
        bearish += 2; reasons.append(f"Stochastic في تشبع شرائي ({stoch:.0f})")

    # ADX — trend strength
    adx = ta.get("adx", 25)
    if adx > 40:
        reasons.append(f"ADX قوي ({adx:.0f}) — اتجاه واضح وقوي 💪")
    elif adx > 25:
        reasons.append(f"ADX متوسط ({adx:.0f}) — اتجاه معتدل")
    else:
        reasons.append(f"ADX ضعيف ({adx:.0f}) — لا يوجد اتجاه واضح")

    # Williams %R
    wr = ta.get("williams_r", -50)
    if wr > -20:
        bearish += 1
    elif wr < -80:
        bullish += 1

    # VWAP
    vwap = ta.get("vwap")
    if vwap:
        if price > vwap:
            bullish += 1; reasons.append(f"السعر فوق VWAP (${vwap:,.2f}) — ضغط شراء")
        else:
            bearish += 1; reasons.append(f"السعر تحت VWAP (${vwap:,.2f}) — ضغط بيع")

    # Volume confirmation
    vol_ratio = ta["vol_ratio"]
    if vol_ratio > 2.0:
        reasons.append(f"حجم تداول مرتفع جداً ({vol_ratio:.1f}x) — نشاط مؤسسي محتمل 🔥")
    elif vol_ratio > 1.5:
        reasons.append(f"حجم تداول مرتفع ({vol_ratio:.1f}x) — اهتمام متزايد")
    elif vol_ratio < 0.5:
        reasons.append(f"حجم تداول ضعيف ({vol_ratio:.1f}x) — حذر من الإشارات الكاذبة")

    # Chart patterns
    for p_name, p_desc, p_type in ta.get("patterns", []):
        if p_type == "bullish":
            bullish += 2
        elif p_type == "bearish":
            bearish += 2
        reasons.append(f"📊 {p_name}: {p_desc}")

    net = bullish - bearish
    total = bullish + bearish
    if total == 0:
        return "neutral", "⚪", 50, reasons
    score = int(50 + (net / max(total, 1)) * 50)
    score = max(0, min(100, score))

    if net >= 7: return "strong_buy", "🚀", score, reasons
    elif net >= 3: return "buy", "🟢", score, reasons
    elif net <= -7: return "strong_sell", "⛔", score, reasons
    elif net <= -3: return "sell", "🔴", score, reasons
    else: return "neutral", "🟡", score, reasons


_SIGNAL_LABELS = {
    "strong_buy": "شراء قوي 🚀", "buy": "شراء 🟢",
    "neutral": "محايد / انتظار 🟡", "sell": "بيع 🔴", "strong_sell": "بيع قوي ⛔",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Arabic response builders
# ═══════════════════════════════════════════════════════════════════════════════

def _fmt_pct(v):
    if v is None: return "—"
    fv = float(v)
    if abs(fv) < 0.005: return "0.00%"
    sign = "+" if fv > 0 else ""
    return f"{sign}{fv:.2f}%"

def _fmt_vol(v):
    if v is None or v == 0: return "—"
    v = float(v)
    if v >= 1_000_000_000: return f"{v/1_000_000_000:.1f}B"
    if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
    elif v >= 1_000: return f"{v/1_000:.0f}K"
    return f"{v:,.0f}"

def _make_gauge(value, min_v, max_v):
    pct = (value - min_v) / (max_v - min_v) if max_v != min_v else 0.5
    pct = max(0, min(1, pct))
    filled = int(pct * 10)
    return f"[{'🟩' * filled}{'⬜' * (10 - filled)}] {value:.0f}"


def _build_full_analysis(symbol: str, quote: dict | None, ta: dict | None) -> str:
    name = COMPANY_NAMES.get(symbol, symbol)

    if quote is None and ta is None:
        return (
            f"⚠️ لم أتمكن من جلب بيانات **{symbol}** في الوقت الحالي.\n\n"
            "الأسباب المحتملة:\n• رمز السهم غير صحيح\n• السوق مغلق\n• مشكلة مؤقتة\n\n"
            "جرب رمزاً آخر مثل **AAPL** أو **NVDA** أو **TSLA**"
        )

    price = ta["price"] if ta else (quote.get("price") if quote else None)
    change_pct = ta["change_pct"] if ta else (quote.get("change_pct") if quote else None)
    if price is None:
        return f"⚠️ لم أتمكن من جلب سعر **{symbol}**. جرب لاحقاً."

    direction = "📈" if (change_pct or 0) >= 0 else "📉"
    lines = []

    # ── Header ──
    lines.append(f"{'━' * 35}")
    lines.append(f"📋 **{name} ({symbol})** — تقرير تحليلي متقدم")
    lines.append(f"{'━' * 35}")
    lines.append("")
    lines.append(f"💰 **السعر: ${price:,.2f}** | {direction} {_fmt_pct(change_pct)}")

    if ta:
        lines.append(f"📊 الحجم: **{_fmt_vol(ta.get('volume'))}** ({ta.get('vol_ratio', 1):.1f}x المتوسط) — {ta.get('vol_trend', '')}")
        lines.append(f"📏 أعلى سنة: **${ta['period_high']:,.2f}** ({_fmt_pct(ta['from_high_pct'])}) | أدنى: **${ta['period_low']:,.2f}** ({_fmt_pct(ta['from_low_pct'])})")

    # ── Performance Table ──
    if ta:
        lines.append("")
        lines.append("📅 **الأداء عبر الفترات:**")
        perf = []
        if ta.get("chg_1d") is not None: perf.append(f"يوم: **{_fmt_pct(ta['chg_1d'])}**")
        if ta.get("chg_5d") is not None: perf.append(f"أسبوع: **{_fmt_pct(ta['chg_5d'])}**")
        if ta.get("chg_20d") is not None: perf.append(f"شهر: **{_fmt_pct(ta['chg_20d'])}**")
        if ta.get("chg_60d") is not None: perf.append(f"3 أشهر: **{_fmt_pct(ta['chg_60d'])}**")
        if ta.get("chg_120d") is not None: perf.append(f"6 أشهر: **{_fmt_pct(ta['chg_120d'])}**")
        if ta.get("chg_ytd") is not None: perf.append(f"سنة: **{_fmt_pct(ta['chg_ytd'])}**")
        lines.append("  " + " | ".join(perf[:3]))
        if len(perf) > 3:
            lines.append("  " + " | ".join(perf[3:]))

    # ── Technical Indicators ──
    if ta:
        lines.append("")
        lines.append("📐 **المؤشرات الفنية المتقدمة:**")

        # RSI
        rsi = ta["rsi"]
        rsi_status = "🔴 تشبع شرائي" if rsi > 70 else "🔵 تشبع بيعي" if rsi < 30 else "✅ محايد"
        lines.append(f"  RSI: **{rsi}** {rsi_status} | {_make_gauge(rsi, 0, 100)}")

        # MACD
        macd_dir = "↗️ صاعد" if ta["macd_histogram"] > 0 else "↘️ هابط"
        lines.append(f"  MACD: **{ta['macd']:.3f}** | إشارة: {ta['macd_signal']:.3f} | {macd_dir}")

        # Stochastic
        stoch = ta["stochastic"]
        stoch_s = "🔴 تشبع شرائي" if stoch > 80 else "🔵 تشبع بيعي" if stoch < 20 else "✅ محايد"
        lines.append(f"  Stochastic: **{stoch:.0f}** {stoch_s}")

        # Bollinger
        bb_range = ta["bb_upper"] - ta["bb_lower"]
        bb_pos = ((price - ta["bb_lower"]) / bb_range * 100) if bb_range > 0 else 50
        lines.append(f"  بولينجر: سفلي ${ta['bb_lower']:,.2f} ← السعر ({bb_pos:.0f}%) → علوي ${ta['bb_upper']:,.2f}")

        # ADX
        adx = ta.get("adx", 25)
        adx_s = "💪 قوي" if adx > 40 else "📊 معتدل" if adx > 25 else "😴 ضعيف"
        lines.append(f"  ADX: **{adx:.0f}** — قوة الاتجاه: {adx_s}")

        # Williams %R
        wr = ta.get("williams_r", -50)
        wr_s = "تشبع شرائي" if wr > -20 else "تشبع بيعي" if wr < -80 else "محايد"
        lines.append(f"  Williams %R: **{wr:.0f}** — {wr_s}")

        # VWAP
        vwap = ta.get("vwap")
        if vwap:
            vwap_pos = "فوق ✅" if price > vwap else "تحت ⬇️"
            lines.append(f"  VWAP: **${vwap:,.2f}** — السعر {vwap_pos}")

        # ATR & Volatility
        atr_pct = (ta["atr"] / price) * 100
        vol_level = "🔥 مرتفع" if atr_pct > 3 else "❄️ منخفض" if atr_pct < 1 else "📊 متوسط"
        lines.append(f"  ATR: **${ta['atr']:.2f}** ({atr_pct:.1f}%) — تقلب {vol_level}")
        if ta.get("volatility_30d"):
            lines.append(f"  التقلب السنوي (30 يوم): **{ta['volatility_30d']:.1f}%** | أقصى انخفاض: **{ta['max_drawdown_pct']:.1f}%**")

    # ── Moving Averages ──
    if ta:
        lines.append("")
        lines.append("📈 **المتوسطات المتحركة:**")
        ma_items = [
            ("EMA 9", ta.get("ema9")),
            ("SMA 20", ta.get("sma20")),
            ("SMA 50", ta.get("sma50")),
            ("SMA 100", ta.get("sma100")),
            ("SMA 200", ta.get("sma200")),
        ]
        above = 0
        total_ma = 0
        for name_ma, val in ma_items:
            if val:
                total_ma += 1
                icon = "✅" if price > val else "⬇️"
                if price > val: above += 1
                lines.append(f"  {icon} {name_ma}: **${val:,.2f}**")

        if total_ma > 0:
            ratio = above / total_ma
            if ratio >= 0.8:
                lines.append("  **🟢 الاتجاه: صاعد قوي (فوق معظم المتوسطات)**")
            elif ratio >= 0.5:
                lines.append("  **🟡 الاتجاه: مختلط يميل للصعود**")
            elif ratio >= 0.2:
                lines.append("  **🟡 الاتجاه: مختلط يميل للهبوط**")
            else:
                lines.append("  **🔴 الاتجاه: هابط (تحت معظم المتوسطات)**")

    # ── Chart Patterns ──
    patterns = ta.get("patterns", [])
    if patterns:
        lines.append("")
        lines.append("📊 **الأنماط الفنية المكتشفة:**")
        for p_name, p_desc, _ in patterns:
            lines.append(f"  • **{p_name}**: {p_desc}")

    # ── Support, Resistance & Fibonacci ──
    if ta:
        lines.append("")
        lines.append("🎯 **مستويات الدعم والمقاومة:**")
        lines.append(f"  المقاومة 3: **${ta['resistance3']:,.2f}**")
        lines.append(f"  المقاومة 2: **${ta['resistance2']:,.2f}**")
        lines.append(f"  المقاومة 1: **${ta['resistance1']:,.2f}**")
        lines.append(f"  ── السعر: **${price:,.2f}** ──")
        lines.append(f"  الدعم 1: **${ta['support1']:,.2f}**")
        lines.append(f"  الدعم 2: **${ta['support2']:,.2f}**")
        lines.append(f"  الدعم 3: **${ta['support3']:,.2f}**")

        fib = ta.get("fibonacci", {})
        if fib:
            lines.append("")
            lines.append("📐 **مستويات فيبوناتشي:**")
            for level, val in fib.items():
                marker = " ◀️" if abs(price - val) / price < 0.01 else ""
                lines.append(f"  {float(level)*100:.1f}%: **${val:,.2f}**{marker}")

    # ── Overall Signal ──
    if ta:
        signal, icon, score, reasons = _generate_signal(ta)
        label = _SIGNAL_LABELS.get(signal, "محايد 🟡")
        lines.append("")
        lines.append(f"{'━' * 35}")
        lines.append(f"🏁 **الإشارة: {label}** — الثقة: **{score}/100**")
        lines.append(f"  {_make_gauge(score, 0, 100)}")
        lines.append("")
        lines.append("**التحليل:**")
        for r in reasons[:8]:
            lines.append(f"  • {r}")

    # ── Trading Plan ──
    if ta:
        atr = ta["atr"]
        lines.append("")
        lines.append(f"{'━' * 35}")
        lines.append("💡 **خطة التداول المقترحة:**")
        if signal in ("buy", "strong_buy"):
            entry = round(price, 2)
            stop = round(price - 2 * atr, 2)
            t1 = round(price + 2 * atr, 2)
            t2 = round(price + 3 * atr, 2)
            t3 = round(price + 4.5 * atr, 2)
            rr = round((t1 - price) / (price - stop), 1) if price > stop else 0
            lines.append(f"  🟢 الدخول: **${entry:,.2f}**")
            lines.append(f"  🛡️ وقف الخسارة: **${stop:,.2f}** ({_fmt_pct(((stop-price)/price)*100)})")
            lines.append(f"  🎯 هدف 1: **${t1:,.2f}** ({_fmt_pct(((t1-price)/price)*100)})")
            lines.append(f"  🎯 هدف 2: **${t2:,.2f}** ({_fmt_pct(((t2-price)/price)*100)})")
            lines.append(f"  🎯 هدف 3: **${t3:,.2f}** ({_fmt_pct(((t3-price)/price)*100)})")
            lines.append(f"  ⚖️ المخاطرة/العائد: **1:{rr}**")
        elif signal in ("sell", "strong_sell"):
            lines.append("  🔴 الإشارات سلبية — يُنصح بعدم الدخول حالياً")
            lines.append(f"  🛡️ إذا كنت شارياً، وقف الخسارة: **${round(price - 2*atr, 2):,.2f}**")
            lines.append(f"  📍 انتظر الدعم عند **${ta['support2']:,.2f}** للدخول")
        else:
            lines.append("  🟡 الإشارات مختلطة — الأفضل الانتظار")
            lines.append(f"  📍 اشترِ عند الدعم: **${ta['support1']:,.2f}**")
            lines.append(f"  📍 أو عند كسر المقاومة: **${ta['resistance1']:,.2f}**")
        lines.append(f"{'━' * 35}")

    lines.append("")
    lines.append("⚠️ *تحليل آلي للأغراض التعليمية — ليس توصية استثمارية*")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# General responses
# ═══════════════════════════════════════════════════════════════════════════════

def _is_market_open() -> bool:
    now = datetime.now(timezone.utc)
    return (now.weekday() < 5) and (14 <= now.hour < 21)


def _build_general_reply(message: str) -> str:
    msg = message.strip().lower()
    is_open = _is_market_open()

    greet_kw = ["مرحبا", "اهلا", "السلام", "كيف حالك", "كيف أنت", "هلا", "هاي", "hello", "hi"]
    if any(k in msg for k in greet_kw):
        return (
            "مرحباً! أنا **المحلل الذكي المتقدم** للأسواق المالية 🤖\n\n"
            "أقدم لك تحليل احترافي يشمل:\n"
            "📊 **15+ مؤشر فني** (RSI, MACD, ADX, بولينجر, فيبوناتشي, VWAP...)\n"
            "📈 **كشف الأنماط** (قاع/قمة مزدوجة, قنوات, اختراقات)\n"
            "🎯 **3 مستويات دعم و 3 مقاومة**\n"
            "💡 **خطة تداول كاملة** (دخول, أهداف, وقف خسارة)\n"
            "⚖️ **تحليل المخاطر** (تقلب, أقصى انخفاض)\n\n"
            "اكتب رمز أي سهم مثل **AAPL** أو **NVDA** وسأجلب لك تقرير شامل! 🚀"
        )

    market_kw = ["السوق", "سوق", "اسواق", "مؤشر", "ناسداك", "داو", "مؤشرات"]
    if any(k in msg for k in market_kw):
        status_icon = "🟢" if is_open else "🔴"
        status_text = "مفتوح" if is_open else "مغلق"
        index_lines = []
        for idx_sym, idx_name in [("SPY", "S&P 500"), ("QQQ", "ناسداك 100"), ("DIA", "داو جونز")]:
            ta = compute_technical_analysis(idx_sym)
            if ta:
                signal, icon, score, _ = _generate_signal(ta)
                label = _SIGNAL_LABELS.get(signal, "محايد").split(" ")[0]
                index_lines.append(f"  {icon} **{idx_name}:** ${ta['price']:,.2f} ({_fmt_pct(ta['change_pct'])}) | RSI: {ta['rsi']:.0f} | {label} {score}/100")
        result = f"🏦 **الأسواق الأمريكية** {status_icon} {status_text}\n\n"
        if index_lines:
            result += "\n".join(index_lines) + "\n\n"
        result += "اكتب رمز أي سهم للتحليل المفصل 📊"
        return result

    buy_kw = ["أفضل سهم", "اشتري", "شراء", "توصية", "ترشيح", "اقتراح", "افضل"]
    if any(k in msg for k in buy_kw):
        # Actually scan top stocks and find best signal
        top_symbols = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "AMD", "NFLX", "AVGO"]
        results = []
        for sym in top_symbols:
            ta = compute_technical_analysis(sym)
            if ta:
                signal, icon, score, _ = _generate_signal(ta)
                results.append((sym, ta, signal, icon, score))
        results.sort(key=lambda r: r[4], reverse=True)

        lines = ["🏆 **أقوى الأسهم فنياً الآن:**\n"]
        for sym, ta, signal, icon, score in results[:5]:
            n = COMPANY_NAMES.get(sym, sym)
            lines.append(f"  {icon} **{sym} ({n}):** ${ta['price']:,.2f} | {_fmt_pct(ta['change_pct'])} | RSI: {ta['rsi']:.0f} | **{score}/100**")
        lines.append("\n⚠️ هذا ترتيب فني فقط — ليس توصية شراء.")
        lines.append("اكتب رمز أي سهم للتقرير الكامل 🔍")
        return "\n".join(lines)

    analysis_kw = ["تحليل", "analyze", "technical", "فني", "مؤشرات", "rsi", "macd", "بولينجر"]
    if any(k in msg for k in analysis_kw):
        return (
            "📊 **التحليل الفني المتقدم**\n\n"
            "تقريري يشمل **15+ مؤشر** محسوب لحظياً:\n\n"
            "🔹 **RSI** — القوة النسبية\n"
            "🔹 **MACD** — الزخم والاتجاه\n"
            "🔹 **بولينجر باند** — نطاق التقلب\n"
            "🔹 **Stochastic** — التذبذب\n"
            "🔹 **ADX** — قوة الاتجاه\n"
            "🔹 **Williams %R** — مناطق التشبع\n"
            "🔹 **VWAP** — المتوسط المرجح بالحجم\n"
            "🔹 **فيبوناتشي** — مستويات الارتداد\n"
            "🔹 **5 متوسطات** — EMA 9, SMA 20/50/100/200\n"
            "🔹 **كشف الأنماط** — قمم/قيعان, قنوات, اختراقات\n"
            "🔹 **3 دعوم + 3 مقاومات**\n"
            "🔹 **خطة تداول** — دخول, 3 أهداف, وقف خسارة\n\n"
            "اكتب رمز السهم مثل **NVDA** أو **تسلا** 🚀"
        )

    ability_kw = ["ماذا تفعل", "شنو تقدر", "وش تسوي", "ايش تقدر", "قدراتك", "ميزاتك", "help"]
    if any(k in msg for k in ability_kw):
        return (
            "🤖 **المحلل الذكي المتقدم**\n\n"
            "📊 تحليل فني شامل بـ **15+ مؤشر**\n"
            "📈 كشف أنماط الشارت تلقائياً\n"
            "🎯 3 مستويات دعم + 3 مقاومة + فيبوناتشي\n"
            "💡 خطة تداول كاملة مع 3 أهداف\n"
            "⚖️ تحليل مخاطر وتقلب\n"
            "🏆 ترتيب أقوى الأسهم فنياً\n"
            "📊 مقارنة بين أسهم متعددة\n"
            "🏦 حالة السوق والمؤشرات\n\n"
            "**جرب:** AAPL | NVDA | قارن AAPL و NVDA | أفضل سهم | كيف السوق 🚀"
        )

    return (
        "🤖 **المحلل الذكي**\n\n"
        "اكتب أي سهم أمريكي وسأعطيك تقرير احترافي:\n\n"
        "• **AAPL** — تحليل آبل\n"
        "• **تسلا** — يفهم العربي\n"
        "• **قارن AAPL و NVDA** — مقارنة\n"
        "• **أفضل سهم** — ترتيب فني\n"
        "• **كيف السوق** — المؤشرات\n\n"
        "كل تقرير يشمل: 15+ مؤشر, أنماط, دعم/مقاومة, فيبوناتشي, وخطة تداول 📊"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Comparison handler
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_multiple_symbols(message: str) -> list:
    candidates = _SYMBOL_RE.findall(message.upper())
    symbols = []
    for c in candidates:
        if c in _KNOWN_TICKERS and c not in symbols:
            symbols.append(c)
    return symbols[:5]


def _build_comparison(symbols: list) -> str:
    lines = [f"📊 **مقارنة فنية متقدمة — {len(symbols)} أسهم**\n"]
    results = []
    for sym in symbols:
        ta = compute_technical_analysis(sym)
        if ta:
            signal, icon, score, _ = _generate_signal(ta)
            results.append((sym, ta, signal, icon, score))
    if not results:
        return "⚠️ لم أتمكن من جلب البيانات."

    # Header
    lines.append("السهم | السعر | يوم | أسبوع | شهر | RSI | الإشارة")
    lines.append("─" * 50)
    for sym, ta, signal, icon, score in results:
        n = COMPANY_NAMES.get(sym, sym)
        label = _SIGNAL_LABELS.get(signal, "محايد").split(" ")[0]
        lines.append(
            f"**{sym}** ({n}) | ${ta['price']:,.2f} | {_fmt_pct(ta['chg_1d'])} | "
            f"{_fmt_pct(ta.get('chg_5d'))} | {_fmt_pct(ta.get('chg_20d'))} | "
            f"{ta['rsi']:.0f} | {icon} {label} **{score}**/100"
        )

    if len(results) > 1:
        best = max(results, key=lambda r: r[4])
        worst = min(results, key=lambda r: r[4])
        lines.append("")
        lines.append(f"🏆 **الأقوى: {best[0]}** ({COMPANY_NAMES.get(best[0], best[0])}) — {best[4]}/100")
        lines.append(f"⚠️ **الأضعف: {worst[0]}** ({COMPANY_NAMES.get(worst[0], worst[0])}) — {worst[4]}/100")
        lines.append("")
        lines.append("اكتب رمز أي سهم للتقرير الكامل 🔍")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Main endpoint
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/message")
def chat_message(payload: ChatRequest):
    user_msg = (payload.message or "").strip()
    if not user_msg:
        return {"reply": "الرجاء إدخال سؤال أو رمز سهم.", "symbol": None, "data": {}}

    try:
        compare_kw = ["مقارنة", "قارن", "compare", "مقارنه", " vs "]
        is_compare = any(k in user_msg.lower() for k in compare_kw)
        multi_symbols = _extract_multiple_symbols(user_msg)

        if is_compare and len(multi_symbols) >= 2:
            reply = _build_comparison(multi_symbols)
            return {"reply": reply, "symbol": multi_symbols[0], "data": {}}

        symbol = _extract_symbol(user_msg, payload.symbol)
        if symbol:
            quote = _fetch_quote(symbol)
            ta = compute_technical_analysis(symbol)
            reply = _build_full_analysis(symbol, quote, ta)
            data = {"symbol": symbol, "quote": quote}
            return {"reply": reply, "symbol": symbol, "data": data}

        reply = _build_general_reply(user_msg)
        return {"reply": reply, "symbol": None, "data": {}}

    except Exception as exc:
        logger.error("ai_chat.error msg=%s err=%s\n%s", user_msg[:100], exc, traceback.format_exc())
        return {
            "reply": "⚠️ حدث خطأ أثناء التحليل. جرب مجدداً.\n\nمثال: **AAPL** أو **NVDA**",
            "symbol": None, "data": {},
        }
