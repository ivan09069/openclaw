"""executor.py — Order execution abstraction (paper / testnet / live)"""
from strategy import Signal
from config import CFG
import db
import logger


async def execute_open(signal: Signal) -> int:
    """
    Open a position. In paper mode, just records it.
    Returns the position DB id.
    """
    if CFG.mode == "paper":
        pos_id = await db.open_position(
            symbol=signal.symbol,
            side=signal.side,
            entry=signal.entry,
            size=signal.size,
            sl=signal.sl,
            tp=signal.tp,
        )
        logger.trade(
            f"PAPER OPEN {signal.side.upper()} {signal.symbol}",
            pos_id=pos_id,
            entry=signal.entry,
            size=signal.size,
            sl=signal.sl,
            tp=signal.tp,
            atr=signal.atr,
            rsi=signal.rsi,
        )
        return pos_id

    # testnet / live
    from market import get_exchange
    ex = get_exchange()
    order_side = "buy" if signal.side == "long" else "sell"
    try:
        order = await ex.create_market_order(signal.symbol, order_side, signal.size)
        filled_price = float(order.get("average") or order.get("price") or signal.entry)
        pos_id = await db.open_position(
            symbol=signal.symbol,
            side=signal.side,
            entry=filled_price,
            size=signal.size,
            sl=signal.sl,
            tp=signal.tp,
        )
        logger.trade(
            f"LIVE OPEN {signal.side.upper()} {signal.symbol}",
            pos_id=pos_id,
            order_id=order.get("id"),
            entry=filled_price,
            size=signal.size,
            sl=signal.sl,
            tp=signal.tp,
        )
        return pos_id
    except Exception as exc:
        logger.error(f"Order failed for {signal.symbol}: {exc}")
        raise


async def execute_close(pos: dict, close_price: float, reason: str) -> float:
    """
    Close a position. In paper mode, just records it.
    Returns realized PnL.
    """
    pnl = await db.close_position(pos["id"], close_price, reason)

    if CFG.mode == "paper":
        logger.trade(
            f"PAPER CLOSE {pos['side'].upper()} {pos['symbol']}",
            pos_id=pos["id"],
            reason=reason,
            close_price=close_price,
            pnl=round(pnl, 4),
        )
        return pnl

    # testnet / live
    from market import get_exchange
    ex = get_exchange()
    # Reverse side to close
    order_side = "sell" if pos["side"] == "long" else "buy"
    try:
        order = await ex.create_market_order(pos["symbol"], order_side, pos["size"])
        logger.trade(
            f"LIVE CLOSE {pos['side'].upper()} {pos['symbol']}",
            pos_id=pos["id"],
            order_id=order.get("id"),
            reason=reason,
            pnl=round(pnl, 4),
        )
    except Exception as exc:
        logger.error(f"Close order failed for {pos['symbol']}: {exc}")
        raise
    return pnl
