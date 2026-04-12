import pandas as pd

try:
    import talib
    TALIB_AVAILABLE = True
except Exception:
    talib = None
    TALIB_AVAILABLE = False


def _calc_cci(high, low, close, period=20):
    tp = (high + low + close) / 3
    sma_tp = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: (abs(x - x.mean())).mean(), raw=False)
    denom = (0.015 * mad).replace(0, pd.NA)
    return (tp - sma_tp) / denom


def _calc_williams_r(high, low, close, period=14):
    highest_high = high.rolling(period).max()
    lowest_low = low.rolling(period).min()
    base = (highest_high - lowest_low).replace(0, pd.NA)
    return -100 * ((highest_high - close) / base)


def _calc_obv(close, volume):
    direction = close.diff().fillna(0)
    signed_volume = volume.where(direction > 0, 0) - volume.where(direction < 0, 0)
    return signed_volume.cumsum()


def _calc_mfi(high, low, close, volume, period=14):
    typical_price = (high + low + close) / 3
    raw_money_flow = typical_price * volume
    tp_delta = typical_price.diff()

    positive_flow = raw_money_flow.where(tp_delta > 0, 0.0)
    negative_flow = raw_money_flow.where(tp_delta < 0, 0.0)

    positive_sum = positive_flow.rolling(period).sum()
    negative_sum = negative_flow.rolling(period).sum().replace(0, 1e-10)

    money_flow_ratio = positive_sum / negative_sum
    return 100 - (100 / (1 + money_flow_ratio))


def _trend_quality_from_row(row):
    score = 0

    if pd.notna(row.get("close")) and pd.notna(row.get("ema20")) and pd.notna(row.get("ema50")):
        if row["close"] > row["ema20"] > row["ema50"]:
            score += 1
        elif row["close"] < row["ema20"] < row["ema50"]:
            score -= 1

    if pd.notna(row.get("adx14")) and pd.notna(row.get("plus_di14")) and pd.notna(row.get("minus_di14")):
        if row["adx14"] >= 25:
            if row["plus_di14"] > row["minus_di14"]:
                score += 1
            elif row["plus_di14"] < row["minus_di14"]:
                score -= 1

    if pd.notna(row.get("roc10")):
        if row["roc10"] > 2:
            score += 1
        elif row["roc10"] < -2:
            score -= 1

    if score > 3:
        score = 3
    elif score < -3:
        score = -3

    return score


def _calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = avg_loss.replace(0, 1e-10)

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _calc_adx(high, low, close, period=14):
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(period).mean().replace(0, 1e-10)
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)

    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10)) * 100
    adx = dx.rolling(period).mean()

    return plus_di, minus_di, adx


def _evaluate_row(row):
    score = 0
    reasons = []

    if pd.notna(row["close"]) and pd.notna(row["ma20"]):
        if row["close"] > row["ma20"]:
            score += 1
            reasons.append("Price > MA20")
        else:
            score -= 1
            reasons.append("Price < MA20")

    if pd.notna(row["ma20"]) and pd.notna(row["ma50"]):
        if row["ma20"] > row["ma50"]:
            score += 1
            reasons.append("MA20 > MA50")
        else:
            score -= 1
            reasons.append("MA20 < MA50")

    if pd.notna(row["rsi14"]):
        if row["rsi14"] < 30:
            score += 1
            reasons.append("RSI oversold")
        elif row["rsi14"] > 70:
            score -= 1
            reasons.append("RSI overbought")
        else:
            reasons.append("RSI neutral")

    if pd.notna(row["macd"]) and pd.notna(row["macd_signal"]):
        if row["macd"] > row["macd_signal"]:
            score += 1
            reasons.append("MACD bullish")
        else:
            score -= 1
            reasons.append("MACD bearish")

    if pd.notna(row["close"]) and pd.notna(row["bb_lower"]) and pd.notna(row["bb_upper"]):
        if row["close"] < row["bb_lower"]:
            score += 1
            reasons.append("Below lower BB")
        elif row["close"] > row["bb_upper"]:
            score -= 1
            reasons.append("Above upper BB")
        else:
            reasons.append("Inside BB")

    if pd.notna(row["volume_ratio"]) and row["volume_ratio"] >= 1.2:
        if pd.notna(row["close"]) and pd.notna(row["ma20"]) and row["close"] > row["ma20"]:
            score += 1
            reasons.append("High volume support")
        elif pd.notna(row["close"]) and pd.notna(row["ma20"]) and row["close"] < row["ma20"]:
            score -= 1
            reasons.append("High volume pressure")
        else:
            reasons.append("High relative volume")

    if pd.notna(row["stoch_k"]) and pd.notna(row["stoch_d"]):
        if row["stoch_k"] > row["stoch_d"] and row["stoch_k"] < 80:
            score += 1
            reasons.append("Stoch bullish")
        elif row["stoch_k"] < row["stoch_d"] and row["stoch_k"] > 20:
            score -= 1
            reasons.append("Stoch bearish")

    if pd.notna(row["adx14"]) and row["adx14"] >= 20:
        reasons.append("Trend strength confirmed")

    if pd.notna(row["close"]) and pd.notna(row["breakout_high_20"]):
        if row["close"] >= row["breakout_high_20"]:
            score += 1
            reasons.append("20D breakout high")

    if pd.notna(row["close"]) and pd.notna(row["breakout_low_20"]):
        if row["close"] <= row["breakout_low_20"]:
            score -= 1
            reasons.append("20D breakdown low")

    advanced_score = 0

    if pd.notna(row.get("cci20")):
        if row["cci20"] < -100:
            advanced_score += 1
            reasons.append("CCI oversold")
        elif row["cci20"] > 100:
            advanced_score -= 1
            reasons.append("CCI overbought")

    if pd.notna(row.get("mfi14")):
        if row["mfi14"] < 20:
            advanced_score += 1
            reasons.append("MFI oversold")
        elif row["mfi14"] > 80:
            advanced_score -= 1
            reasons.append("MFI overbought")

    if pd.notna(row.get("obv")) and pd.notna(row.get("obv_ema20")) and pd.notna(row.get("roc10")):
        if row["obv"] > row["obv_ema20"] and row["roc10"] > 1:
            advanced_score += 1
            reasons.append("OBV trend support")
        elif row["obv"] < row["obv_ema20"] and row["roc10"] < -1:
            advanced_score -= 1
            reasons.append("OBV trend pressure")

    if pd.notna(row.get("willr14")) and pd.notna(row.get("stoch_k")):
        if row["willr14"] <= -80 and row["stoch_k"] < 30:
            advanced_score += 1
            reasons.append("Williams oversold")
        elif row["willr14"] >= -20 and row["stoch_k"] > 70:
            advanced_score -= 1
            reasons.append("Williams overbought")

    if pd.notna(row.get("dist_from_52w_high_pct")) and pd.notna(row.get("close")) and pd.notna(row.get("ma20")):
        if row["dist_from_52w_high_pct"] >= -3 and row["close"] > row["ma20"]:
            advanced_score += 1
            reasons.append("Near 52W high")
        elif pd.notna(row.get("dist_from_52w_low_pct")) and row["dist_from_52w_low_pct"] <= 3 and row["close"] < row["ma20"]:
            advanced_score -= 1
            reasons.append("Near 52W low")

    if pd.notna(row.get("gap_pct")) and pd.notna(row.get("close")) and pd.notna(row.get("ma20")):
        if row["gap_pct"] >= 1.0 and row["close"] > row["ma20"]:
            advanced_score += 1
            reasons.append("Bullish gap")
        elif row["gap_pct"] <= -1.0 and row["close"] < row["ma20"]:
            advanced_score -= 1
            reasons.append("Bearish gap")

    candle_signal = str(row.get("candle_signal", "NONE"))
    if candle_signal in ["BULLISH_ENGULFING", "HAMMER"]:
        advanced_score += 1
        reasons.append(f"Candlestick bullish ({candle_signal})")
    elif candle_signal in ["BEARISH_ENGULFING", "SHOOTING_STAR"]:
        advanced_score -= 1
        reasons.append(f"Candlestick bearish ({candle_signal})")
    elif candle_signal == "DOJI":
        reasons.append("Doji indecision")

    if pd.notna(row.get("trend_quality_score")):
        if row["trend_quality_score"] >= 2:
            advanced_score += 1
            reasons.append("Trend quality bullish")
        elif row["trend_quality_score"] <= -2:
            advanced_score -= 1
            reasons.append("Trend quality bearish")

    if bool(row.get("squeeze_ready", False)):
        reasons.append("Squeeze ready")

    if advanced_score > 1:
        advanced_score = 1
    elif advanced_score < -1:
        advanced_score = -1

    score += advanced_score

    if score >= 4:
        final_signal = "BUY"
    elif score <= -4:
        final_signal = "SELL"
    else:
        final_signal = "HOLD"

    return pd.Series({
        "technical_score": score,
        "final_signal": final_signal,
        "reasons": "; ".join(reasons)
    })


def calculate_technical_indicators(df):
    df = df.copy()

    numeric_cols = ["open", "high", "low", "close", "volume"]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")

    df = df.sort_values("datetime").reset_index(drop=True)

    df["ma20"] = df["close"].rolling(20).mean()
    df["ma50"] = df["close"].rolling(50).mean()

    prev_close = df["close"].shift(1)

    if TALIB_AVAILABLE:
        try:
            close_arr = df["close"].to_numpy(dtype=float)
            high_arr = df["high"].to_numpy(dtype=float)
            low_arr = df["low"].to_numpy(dtype=float)
            volume_arr = df["volume"].to_numpy(dtype=float)

            df["ema20"] = talib.EMA(close_arr, timeperiod=20)
            df["ema50"] = talib.EMA(close_arr, timeperiod=50)

            df["rsi14"] = talib.RSI(close_arr, timeperiod=14)

            macd, macd_signal, macd_hist = talib.MACD(
                close_arr,
                fastperiod=12,
                slowperiod=26,
                signalperiod=9
            )
            df["macd"] = macd
            df["macd_signal"] = macd_signal
            df["macd_hist"] = macd_hist

            bb_upper, bb_mid, bb_lower = talib.BBANDS(
                close_arr,
                timeperiod=20,
                nbdevup=2,
                nbdevdn=2,
                matype=0
            )
            df["bb_mid"] = bb_mid
            df["bb_upper"] = bb_upper
            df["bb_lower"] = bb_lower
            df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"].replace(0, pd.NA)

            df["atr14"] = talib.ATR(high_arr, low_arr, close_arr, timeperiod=14)

            slowk, slowd = talib.STOCH(
                high_arr,
                low_arr,
                close_arr,
                fastk_period=14,
                slowk_period=3,
                slowk_matype=0,
                slowd_period=3,
                slowd_matype=0
            )
            df["stoch_k"] = slowk
            df["stoch_d"] = slowd

            df["plus_di14"] = talib.PLUS_DI(high_arr, low_arr, close_arr, timeperiod=14)
            df["minus_di14"] = talib.MINUS_DI(high_arr, low_arr, close_arr, timeperiod=14)
            df["adx14"] = talib.ADX(high_arr, low_arr, close_arr, timeperiod=14)

            tr_df = pd.concat(
                [
                    df["high"] - df["low"],
                    (df["high"] - prev_close).abs(),
                    (df["low"] - prev_close).abs()
                ],
                axis=1
            )
            df["tr"] = tr_df.max(axis=1)
        except Exception:
            df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
            df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

            df["rsi14"] = _calc_rsi(df["close"], 14)

            ema12 = df["close"].ewm(span=12, adjust=False).mean()
            ema26 = df["close"].ewm(span=26, adjust=False).mean()
            df["macd"] = ema12 - ema26
            df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
            df["macd_hist"] = df["macd"] - df["macd_signal"]

            rolling_std20 = df["close"].rolling(20).std()
            df["bb_mid"] = df["ma20"]
            df["bb_upper"] = df["ma20"] + (rolling_std20 * 2)
            df["bb_lower"] = df["ma20"] - (rolling_std20 * 2)
            df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"].replace(0, pd.NA)

            tr_df = pd.concat(
                [
                    df["high"] - df["low"],
                    (df["high"] - prev_close).abs(),
                    (df["low"] - prev_close).abs()
                ],
                axis=1
            )
            df["tr"] = tr_df.max(axis=1)
            df["atr14"] = df["tr"].rolling(14).mean()

            low14 = df["low"].rolling(14).min()
            high14 = df["high"].rolling(14).max()
            stoch_base = (high14 - low14).replace(0, pd.NA)
            df["stoch_k"] = ((df["close"] - low14) / stoch_base) * 100
            df["stoch_d"] = df["stoch_k"].rolling(3).mean()

            plus_di, minus_di, adx = _calc_adx(df["high"], df["low"], df["close"], 14)
            df["plus_di14"] = plus_di
            df["minus_di14"] = minus_di
            df["adx14"] = adx
    else:
        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

        df["rsi14"] = _calc_rsi(df["close"], 14)

        ema12 = df["close"].ewm(span=12, adjust=False).mean()
        ema26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema12 - ema26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        rolling_std20 = df["close"].rolling(20).std()
        df["bb_mid"] = df["ma20"]
        df["bb_upper"] = df["ma20"] + (rolling_std20 * 2)
        df["bb_lower"] = df["ma20"] - (rolling_std20 * 2)
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"].replace(0, pd.NA)

        tr_df = pd.concat(
            [
                df["high"] - df["low"],
                (df["high"] - prev_close).abs(),
                (df["low"] - prev_close).abs()
            ],
            axis=1
        )
        df["tr"] = tr_df.max(axis=1)
        df["atr14"] = df["tr"].rolling(14).mean()

        low14 = df["low"].rolling(14).min()
        high14 = df["high"].rolling(14).max()
        stoch_base = (high14 - low14).replace(0, pd.NA)
        df["stoch_k"] = ((df["close"] - low14) / stoch_base) * 100
        df["stoch_d"] = df["stoch_k"].rolling(3).mean()

        plus_di, minus_di, adx = _calc_adx(df["high"], df["low"], df["close"], 14)
        df["plus_di14"] = plus_di
        df["minus_di14"] = minus_di
        df["adx14"] = adx

    df["vol_ma20"] = df["volume"].rolling(20).mean()
    df["volume_ratio"] = df["volume"] / df["vol_ma20"]
    df["volume_ratio"] = df["volume_ratio"].replace([float("inf"), float("-inf")], pd.NA)

    df["returns"] = df["close"].pct_change()
    df["volatility20"] = df["returns"].rolling(20).std() * (252 ** 0.5)

    df["breakout_high_20"] = df["high"].rolling(20).max()
    df["breakout_low_20"] = df["low"].rolling(20).min()

    df["high_52w"] = df["high"].rolling(252).max()
    df["low_52w"] = df["low"].rolling(252).min()
    df["dist_from_52w_high_pct"] = ((df["close"] / df["high_52w"]) - 1) * 100
    df["dist_from_52w_low_pct"] = ((df["close"] / df["low_52w"]) - 1) * 100
    df["gap_pct"] = ((df["open"] - prev_close) / prev_close.replace(0, pd.NA)) * 100
    df["gap_signal"] = "NONE"
    df.loc[df["gap_pct"] >= 1.0, "gap_signal"] = "GAP_UP"
    df.loc[df["gap_pct"] <= -1.0, "gap_signal"] = "GAP_DOWN"

    prev_open = df["open"].shift(1)
    body = (df["close"] - df["open"]).abs()
    candle_range = (df["high"] - df["low"]).replace(0, pd.NA)
    upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
    lower_wick = df[["open", "close"]].min(axis=1) - df["low"]

    if TALIB_AVAILABLE:
        try:
            open_arr = df["open"].to_numpy(dtype=float)
            high_arr = df["high"].to_numpy(dtype=float)
            low_arr = df["low"].to_numpy(dtype=float)
            close_arr = df["close"].to_numpy(dtype=float)

            df["doji"] = talib.CDLDOJI(open_arr, high_arr, low_arr, close_arr) != 0
            df["hammer"] = talib.CDLHAMMER(open_arr, high_arr, low_arr, close_arr) > 0
            df["shooting_star"] = talib.CDLSHOOTINGSTAR(open_arr, high_arr, low_arr, close_arr) < 0

            engulf = talib.CDLENGULFING(open_arr, high_arr, low_arr, close_arr)
            df["bullish_engulfing"] = engulf > 0
            df["bearish_engulfing"] = engulf < 0
        except Exception:
            df["doji"] = (body / candle_range) <= 0.10
            df["hammer"] = (lower_wick >= (body * 2)) & (upper_wick <= (body * 1.2))
            df["shooting_star"] = (upper_wick >= (body * 2)) & (lower_wick <= (body * 1.2))

            df["bullish_engulfing"] = (
                (prev_close < prev_open) &
                (df["close"] > df["open"]) &
                (df["open"] <= prev_close) &
                (df["close"] >= prev_open)
            )

            df["bearish_engulfing"] = (
                (prev_close > prev_open) &
                (df["close"] < df["open"]) &
                (df["open"] >= prev_close) &
                (df["close"] <= prev_open)
            )
    else:
        df["doji"] = (body / candle_range) <= 0.10
        df["hammer"] = (lower_wick >= (body * 2)) & (upper_wick <= (body * 1.2))
        df["shooting_star"] = (upper_wick >= (body * 2)) & (lower_wick <= (body * 1.2))

        df["bullish_engulfing"] = (
            (prev_close < prev_open) &
            (df["close"] > df["open"]) &
            (df["open"] <= prev_close) &
            (df["close"] >= prev_open)
        )

        df["bearish_engulfing"] = (
            (prev_close > prev_open) &
            (df["close"] < df["open"]) &
            (df["open"] >= prev_close) &
            (df["close"] <= prev_open)
        )

    df["candle_signal"] = "NONE"
    df.loc[df["doji"] == True, "candle_signal"] = "DOJI"
    df.loc[df["hammer"] == True, "candle_signal"] = "HAMMER"
    df.loc[df["shooting_star"] == True, "candle_signal"] = "SHOOTING_STAR"
    df.loc[df["bullish_engulfing"] == True, "candle_signal"] = "BULLISH_ENGULFING"
    df.loc[df["bearish_engulfing"] == True, "candle_signal"] = "BEARISH_ENGULFING"

    df["roc10"] = df["close"].pct_change(10) * 100
    df["cci20"] = _calc_cci(df["high"], df["low"], df["close"], 20)
    df["willr14"] = _calc_williams_r(df["high"], df["low"], df["close"], 14)
    df["obv"] = _calc_obv(df["close"], df["volume"])
    df["obv_ema20"] = df["obv"].ewm(span=20, adjust=False).mean()
    df["mfi14"] = _calc_mfi(df["high"], df["low"], df["close"], df["volume"], 14)

    bb_width_floor = df["bb_width"].rolling(120).quantile(0.20)
    df["squeeze_ready"] = (df["bb_width"] <= bb_width_floor) & (df["adx14"] < 20)
    df["trend_quality_score"] = df.apply(_trend_quality_from_row, axis=1)

    score_df = df.apply(_evaluate_row, axis=1)
    df = pd.concat([df, score_df], axis=1)

    return df
