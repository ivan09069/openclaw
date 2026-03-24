"""risk.py — Position sizing, exposure, daily-loss, cooldown, kill-switch

All checks are synchronous (state passed in); async daily_pnl check is
done in bot.py before calling here.
"""

import os
import time
from config import CFG
import logger

# In-memory cooldown tracker  {symbol: last_signal_timestamp}
_cooldowns: dict[str, float] = {}


# ── Kill-switch ──────────────────────────────────────────────────────────────

def kill_switch_active() -> bool:
    """Returns True if data/KILL file exists. Touch it to stop the bot."""
    return os.path.exists(CFG.kill_file)


# ── Position sizing ──────────────────────────────────────────────────────────

def position_size(price: float, atr: float, equity: float) -> float:
    """
    Risk-based sizing:
      risk_dollars = equity * RISK_PER_TRADE
      stop_distance = atr * ATR_SL_MULT
      size (base) = risk_dollars / stop_distance
    Minimum size guard: at least $10 notional.
    """
    if atr <= 0 or price <= 0:
        return 0.0
    risk_dollars   = equity * CFG.risk_per_trade
    stop_distance  = atr * CFG.atr_sl_mult
    size           = risk_dollars / stop_distance
    notional       = size * price
    if notional < 10:
        logger.risk("size too small, skipping", notional=round(notional, 2))
        return 0.0
    return size


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
) -> tuple[bool, str]:
    """
    Returns (allowed, reason).
    Checks (in order):
      1. Kill-switch file
      2. Daily loss halt flag
      3. Daily loss threshold
      4. Max concurrent positions
      5. Max exposure cap
      6. Cooldown
      7. Duplicate symbol already open
    """
    # 1. Kill-switch
    if kill_switch_active():
        return False, "kill-switch active"

    # 2. Halted flag (persisted from previous session)
    if halted:
        return False, "trading halted for today (daily loss limit hit)"

    # 3. Daily loss
    loss_limit = equity * CFG.max_daily_loss
    if daily_pnl <= -abs(loss_limit):
        logger.risk("daily loss limit hit", daily_pnl=round(daily_pnl, 2),
                    limit=-round(loss_limit, 2))
        return False, f"daily loss limit reached ({daily_pnl:.2f})"

    # 4. Max positions
    open_count = len([p for p in open_positions if p["status"] == "open"])
    if open_count >= CFG.max_positions:
        return False, f"max positions ({CFG.max_positions}) reached"

    # 5. Exposure cap
    open_notional = sum(p["size"] * p["entry_price"] for p in open_positions
                        if p["status"] == "open")
    new_notional  = size * price
    if (open_notional + new_notional) / equity > CFG.max_exposure:
        return False, (
            f"exposure cap: {(open_notional+new_notional)/equity:.1%} > {CFG.max_exposure:.1%}"
        )

    # 6. Cooldown
    last = _cooldowns.get(symbol, 0)
    elapsed = time.time() - last
    if elapsed < CFG.cooldown_seconds:
        remaining = int(CFG.cooldown_seconds - elapsed)
        return False, f"cooldown {remaining}s remaining for {symbol}"

    # 7. Duplicate symbol
    open_syms = [p["symbol"] for p in open_positions if p["status"] == "open"]
    if symbol in open_syms:
        return False, f"already have open position in {symbol}"

    return True, "ok"


def record_signal(symbol: str) -> None:
    """Call after a trade is opened to start cooldown."""
    _cooldowns[symbol] = time.time()


# ── Exit check ───────────────────────────────────────────────────────────────

def should_exit(position: dict, current_price: float) -> tuple[bool, str]:
    """
    Check if current price has hit SL or TP.
    Returns (should_exit, reason).
    """
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
