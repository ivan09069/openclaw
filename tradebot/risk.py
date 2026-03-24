"""risk.py — Position sizing, exposure, daily-loss, cooldown, kill-switch, spread guard

Pre-trade gate order:
  1. Kill-switch
  2. Daily halt flag
  3. Daily loss threshold
  4. Max concurrent positions
  5. Max exposure cap
  6. Cooldown
  7. Duplicate symbol
  8. Spread / slippage check   ← new
  9. ATR validity              ← new
"""

import os
import math
import time
from config import CFG
import logger

# In-memory cooldown tracker  {symbol: last_signal_epoch}
_cooldowns: dict[str, float] = {}


# ── Kill-switch ───────────────────────────────────────────────────────────────

def kill_switch_active() -> bool:
    """Returns True if the KILL file exists."""
    return os.path.exists(CFG.kill_file)


# ── Position sizing ───────────────────────────────────────────────────────────

def position_size(price: float, atr: float, equity: float) -> float:
    """
    Risk-based sizing:
      risk_dollars  = equity * RISK_PER_TRADE
      stop_distance = atr * ATR_SL_MULT
      size (base)   = risk_dollars / stop_distance

    Returns 0 if ATR is invalid or notional < $10.
    """
    if atr <= 0 or not math.isfinite(atr):
        logger.risk("sizing rejected: invalid ATR", atr=atr)
        return 0.0
    if price <= 0 or not math.isfinite(price):
        logger.risk("sizing rejected: invalid price", price=price)
        return 0.0

    risk_dollars  = equity * CFG.risk_per_trade
    stop_distance = atr * CFG.atr_sl_mult
    size          = risk_dollars / stop_distance
    notional      = size * price

    if notional < 10:
        logger.risk("size too small, skipping", notional=round(notional, 2))
        return 0.0
    return size


# ── Spread / slippage check ───────────────────────────────────────────────────

def spread_ok(ticker: dict) -> tuple[bool, str]:
    """
    Returns (ok, reason).
    Checks bid/ask spread against MAX_SPREAD_PCT.
    Fails safe: if bid or ask is missing/zero, rejects.
    """
    bid = ticker.get("bid", 0.0)
    ask = ticker.get("ask", 0.0)

    if not bid or not ask or bid <= 0 or ask <= 0:
        return False, "bid or ask unavailable — rejecting for safety"

    mid    = (bid + ask) / 2
    spread = (ask - bid) / mid if mid > 0 else 1.0

    if spread > CFG.max_spread_pct:
        return False, (
            f"spread {spread:.4%} exceeds max {CFG.max_spread_pct:.4%} "
            f"(bid={bid} ask={ask})"
        )
    return True, "ok"


# ── Pre-trade gate ────────────────────────────────────────────────────────────

def can_trade(
    symbol: str,
    signal: str,
    open_positions: list,
    equity: float,
    daily_pnl: float,
    halted: bool,
    size: float,
    price: float,
    ticker: dict = None,
    atr: float = 0.0,
) -> tuple[bool, str]:
    """
    Returns (allowed, reason).
    Pass ticker dict for spread check; pass atr for validity check.
    """
    # 1. Kill-switch
    if kill_switch_active():
        return False, "kill-switch active"

    # 2. Halted flag
    if halted:
        return False, "trading halted for today (daily loss limit hit)"

    # 3. Daily loss threshold
    loss_limit = equity * CFG.max_daily_loss
    if daily_pnl <= -abs(loss_limit):
        logger.risk(
            "daily loss limit hit",
            daily_pnl=round(daily_pnl, 2),
            limit=-round(loss_limit, 2),
        )
        return False, f"daily loss limit reached ({daily_pnl:.2f})"

    # 4. Max concurrent positions
    open_count = sum(1 for p in open_positions if p["status"] == "open")
    if open_count >= CFG.max_positions:
        return False, f"max positions ({CFG.max_positions}) reached"

    # 5. Exposure cap
    open_notional = sum(
        p["size"] * p["entry_price"]
        for p in open_positions if p["status"] == "open"
    )
    new_notional = size * price
    total_exposure = (open_notional + new_notional) / equity if equity > 0 else 1.0
    if total_exposure > CFG.max_exposure:
        return False, (
            f"exposure cap: {total_exposure:.1%} > {CFG.max_exposure:.1%}"
        )

    # 6. Cooldown
    last    = _cooldowns.get(symbol, 0)
    elapsed = time.time() - last
    if elapsed < CFG.cooldown_seconds:
        remaining = int(CFG.cooldown_seconds - elapsed)
        return False, f"cooldown {remaining}s remaining for {symbol}"

    # 7. Duplicate symbol
    open_syms = [p["symbol"] for p in open_positions if p["status"] == "open"]
    if symbol in open_syms:
        return False, f"already have open position in {symbol}"

    # 8. Spread check
    if ticker is not None:
        ok, reason = spread_ok(ticker)
        if not ok:
            return False, f"spread check failed: {reason}"

    # 9. ATR validity
    if atr <= 0 or not math.isfinite(atr):
        return False, f"invalid ATR ({atr}) — refusing entry"

    return True, "ok"


def record_signal(symbol: str) -> None:
    """Call after a trade is opened to start the cooldown timer."""
    _cooldowns[symbol] = time.time()


def cooldown_state() -> dict[str, int]:
    """
    Returns {symbol: seconds_remaining} for symbols currently in cooldown.
    Only includes symbols that still have time left.
    """
    now = time.time()
    result = {}
    for sym, ts in _cooldowns.items():
        remaining = int(CFG.cooldown_seconds - (now - ts))
        if remaining > 0:
            result[sym] = remaining
    return result


# ── Exit check ────────────────────────────────────────────────────────────────

def should_exit(position: dict, current_price: float) -> tuple[bool, str]:
    """Returns (should_exit, reason): 'stop_loss' | 'take_profit' | ''."""
    side = position["side"]
    sl   = position["sl"]
    tp   = position["tp"]

    if side == "long":
        if current_price <= sl:
            return True, "stop_loss"
        if current_price >= tp:
            return True, "take_profit"
    elif side == "short":
        if current_price >= sl:
            return True, "stop_loss"
        if current_price <= tp:
            return True, "take_profit"

    return False, ""
