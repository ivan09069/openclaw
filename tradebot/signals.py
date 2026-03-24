"""signals.py — EMA crossover + RSI filter + ATR  (pure pandas, no pandas_ta)

EMA:  standard exponential moving average (adjust=False)
RSI:  Wilder smoothing (equivalent to EMA with alpha=1/period)
ATR:  Wilder smoothing of true-range

Signal:
  LONG  — EMA_fast crosses above EMA_slow AND RSI > rsi_long_threshold
  SHORT — EMA_fast crosses below EMA_slow AND RSI < rsi_short_threshold
  FLAT  — otherwise
"""

import pandas as pd
from config import CFG
import logger


# ── Indicators ────────────────────────────────────────────────────────────────

def _ema(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(span=period, adjust=False).mean()


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    alpha = 1.0 / period
    avg_gain = gain.ewm(alpha=alpha, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    alpha = 1.0 / period
    return tr.ewm(alpha=alpha, adjust=False).mean()


# ── Main entry ────────────────────────────────────────────────────────────────

def compute(ohlcv: list) -> dict:
    """
    ohlcv: list of [timestamp_ms, open, high, low, close, volume]
    Returns signal dict.
    """
    min_rows = max(CFG.ema_slow, CFG.rsi_period, CFG.atr_period) + 10
    if len(ohlcv) < min_rows:
        logger.warn("signals: not enough candles", count=len(ohlcv), need=min_rows)
        return _flat(0.0)

    df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
    df = df.astype({"open": float, "high": float, "low": float,
                    "close": float, "volume": float})

    df["ema_fast"] = _ema(df["close"], CFG.ema_fast)
    df["ema_slow"] = _ema(df["close"], CFG.ema_slow)
    df["rsi"]      = _rsi(df["close"], CFG.rsi_period)
    df["atr"]      = _atr(df["high"], df["low"], df["close"], CFG.atr_period)

    df.dropna(inplace=True)
    if len(df) < 2:
        logger.warn("signals: insufficient data after dropna")
        return _flat(0.0)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price   = float(last["close"])
    atr     = float(last["atr"])
    rsi     = float(last["rsi"])
    ef_now  = float(last["ema_fast"])
    es_now  = float(last["ema_slow"])
    ef_prev = float(prev["ema_fast"])
    es_prev = float(prev["ema_slow"])

    crossed_up   = ef_prev <= es_prev and ef_now > es_now
    crossed_down = ef_prev >= es_prev and ef_now < es_now

    if crossed_up and rsi > CFG.rsi_long_threshold:
        signal = "long"
    elif crossed_down and rsi < CFG.rsi_short_threshold:
        signal = "short"
    else:
        signal = "flat"

    return {
        "signal":   signal,
        "price":    price,
        "atr":      atr,
        "rsi":      round(rsi, 2),
        "ema_fast": round(ef_now, 4),
        "ema_slow": round(es_now, 4),
    }


def sl_tp(signal: str, price: float, atr: float) -> tuple:
    sl_dist = atr * CFG.atr_sl_mult
    tp_dist = atr * CFG.atr_tp_mult
    if signal == "long":
        return price - sl_dist, price + tp_dist
    elif signal == "short":
        return price + sl_dist, price - tp_dist
    return 0.0, 0.0


def _flat(price: float) -> dict:
    return {"signal": "flat", "price": price, "atr": 0.0,
            "rsi": 0.0, "ema_fast": 0.0, "ema_slow": 0.0}
