"""strategy.py — EMA crossover + RSI filter + ATR sizing

Signal logic:
  LONG  when ema_fast crosses above ema_slow AND rsi > RSI_LONG_THRESHOLD
  SHORT when ema_fast crosses below ema_slow AND rsi < RSI_SHORT_THRESHOLD

Position sizing:
  risk_amount = capital * RISK_PER_TRADE
  stop_distance = atr * ATR_SL_MULT
  size = risk_amount / stop_distance

Fallback (if ATR=0): use 0.5% of price as stop distance.
"""
import pandas as pd
from dataclasses import dataclass
from typing import Optional
from config import CFG


@dataclass
class Signal:
    symbol: str
    side: str            # 'long' | 'short'
    entry: float
    sl: float
    tp: float
    size: float          # base units
    atr: float
    rsi: float


def compute_signal(symbol: str, df: pd.DataFrame, capital: float) -> Optional[Signal]:
    if len(df) < 3:
        return None

    ef = f"ema{CFG.ema_fast}"
    es = f"ema{CFG.ema_slow}"

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    ema_fast_curr, ema_fast_prev = curr[ef], prev[ef]
    ema_slow_curr, ema_slow_prev = curr[es], prev[es]
    rsi  = float(curr["rsi"])
    atr  = float(curr["atr"]) if curr["atr"] > 0 else curr["close"] * 0.005
    price = float(curr["close"])

    # Cross detection
    crossed_up   = (ema_fast_prev <= ema_slow_prev) and (ema_fast_curr > ema_slow_curr)
    crossed_down = (ema_fast_prev >= ema_slow_prev) and (ema_fast_curr < ema_slow_curr)

    side = None
    if crossed_up   and rsi > CFG.rsi_long_threshold:
        side = "long"
    elif crossed_down and rsi < CFG.rsi_short_threshold:
        side = "short"

    if side is None:
        return None

    # Sizing
    risk_amount    = capital * CFG.risk_per_trade
    stop_distance  = atr * CFG.atr_sl_mult
    size           = risk_amount / stop_distance  # base units

    if side == "long":
        sl = price - stop_distance
        tp = price + atr * CFG.atr_tp_mult
    else:
        sl = price + stop_distance
        tp = price - atr * CFG.atr_tp_mult

    return Signal(
        symbol=symbol,
        side=side,
        entry=price,
        sl=round(sl, 8),
        tp=round(tp, 8),
        size=round(size, 6),
        atr=round(atr, 8),
        rsi=round(rsi, 2),
    )
