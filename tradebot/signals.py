"""signals.py — EMA crossover + RSI filter + ATR for SL/TP/sizing

Signal logic:
  LONG  when EMA_fast crosses ABOVE EMA_slow AND RSI > rsi_long_threshold
  SHORT when EMA_fast crosses BELOW EMA_slow AND RSI < rsi_short_threshold
  Flat  otherwise

Returns:
  {
    "signal":  "long" | "short" | "flat",
    "price":   float,   # close of last candle
    "atr":     float,   # ATR(14) of last candle
    "rsi":     float,
    "ema_fast": float,
    "ema_slow": float,
  }
"""

import pandas as pd
import pandas_ta as ta
from config import CFG
import logger


def compute(ohlcv: list) -> dict:
    """
    ohlcv: list of [timestamp_ms, open, high, low, close, volume]
    Must have at least CFG.ema_slow + CFG.atr_period + 5 rows.
    """
    if len(ohlcv) < CFG.ema_slow + CFG.atr_period + 5:
        logger.warn("signals: not enough candles", count=len(ohlcv))
        return _flat(0.0)

    df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
    df = df.astype({"open": float, "high": float, "low": float, "close": float, "volume": float})

    # Indicators
    df["ema_fast"] = ta.ema(df["close"], length=CFG.ema_fast)
    df["ema_slow"] = ta.ema(df["close"], length=CFG.ema_slow)
    df["rsi"]      = ta.rsi(df["close"], length=CFG.rsi_period)
    atr_series     = ta.atr(df["high"], df["low"], df["close"], length=CFG.atr_period)
    df["atr"]      = atr_series

    df.dropna(inplace=True)
    if len(df) < 2:
        logger.warn("signals: insufficient data after dropna")
        return _flat(0.0)

    last  = df.iloc[-1]
    prev  = df.iloc[-2]

    price    = float(last["close"])
    atr      = float(last["atr"])
    rsi      = float(last["rsi"])
    ef_now   = float(last["ema_fast"])
    es_now   = float(last["ema_slow"])
    ef_prev  = float(prev["ema_fast"])
    es_prev  = float(prev["ema_slow"])

    # Cross detection
    crossed_up   = ef_prev <= es_prev and ef_now > es_now
    crossed_down = ef_prev >= es_prev and ef_now < es_now

    if crossed_up and rsi > CFG.rsi_long_threshold:
        sig = "long"
    elif crossed_down and rsi < CFG.rsi_short_threshold:
        sig = "short"
    else:
        sig = "flat"

    return {
        "signal":   sig,
        "price":    price,
        "atr":      atr,
        "rsi":      round(rsi, 2),
        "ema_fast": round(ef_now, 4),
        "ema_slow": round(es_now, 4),
    }


def sl_tp(signal: str, price: float, atr: float) -> tuple[float, float]:
    """Return (stop_loss, take_profit) prices."""
    sl_dist = atr * CFG.atr_sl_mult
    tp_dist = atr * CFG.atr_tp_mult
    if signal == "long":
        return price - sl_dist, price + tp_dist
    elif signal == "short":
        return price + sl_dist, price - tp_dist
    return 0.0, 0.0


def _flat(price: float) -> dict:
    return {"signal": "flat", "price": price, "atr": 0.0, "rsi": 0.0,
            "ema_fast": 0.0, "ema_slow": 0.0}
