"""bot.py — Main trading loop

Flow per symbol per tick:
  1. Kill-switch check (file + daily halt)
  2. Fetch OHLCV
  3. Compute signals
  4. Check exits on open positions
  5. Check entry conditions via risk gate
  6. Execute (paper/testnet/live)
  7. Persist + log

Run:
  python bot.py
"""

import asyncio
import signal
import sys
import os
from datetime import datetime

from config import CFG
from exchange import build_exchange
import db
import risk
import signals as sig
import logger
import health


# ── Graceful shutdown ─────────────────────────────────────────────────────────

_shutdown = asyncio.Event()

def _handle_signal(signum, frame):
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    _shutdown.set()

signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ── Exit management ───────────────────────────────────────────────────────────

async def check_exits(ex) -> None:
    """Scan open positions, exit any that hit SL or TP."""
    open_pos = await db.get_open_positions()
    for pos in open_pos:
        ticker = await ex.fetch_ticker(pos["symbol"])
        price  = ticker["last"]
        if price <= 0:
            continue

        should_exit, reason = risk.should_exit(pos, price)
        if should_exit:
            pnl = await db.close_position(pos["id"], price, reason)
            logger.trade(
                "CLOSE",
                symbol=pos["symbol"],
                side=pos["side"],
                entry=pos["entry_price"],
                exit=price,
                pnl=round(pnl, 4),
                reason=reason,
                id=pos["id"],
            )
            # Update paper equity
            if CFG.mode == "paper":
                ex.equity += pnl


# ── Entry logic ───────────────────────────────────────────────────────────────

async def try_entry(ex, symbol: str) -> None:
    """Fetch candles, compute signal, validate risk, open if green."""
    ohlcv = await ex.fetch_ohlcv(symbol, CFG.timeframe, CFG.ohlcv_limit)
    if not ohlcv:
        logger.warn("No OHLCV data", symbol=symbol)
        return

    result = sig.compute(ohlcv)
    signal  = result["signal"]
    price   = result["price"]
    atr     = result["atr"]

    if signal == "flat":
        return

    logger.info(
        f"Signal {signal.upper()} {symbol}",
        rsi=result["rsi"], ema_fast=result["ema_fast"], ema_slow=result["ema_slow"]
    )

    equity     = ex.equity
    size       = risk.position_size(price, atr, equity)
    if size <= 0:
        return

    open_pos   = await db.get_open_positions()
    daily_pnl  = await db.get_daily_pnl()
    halted     = await db.is_halted()

    allowed, reason = risk.can_trade(
        symbol, signal, open_pos, equity, daily_pnl, halted, size, price
    )

    if not allowed:
        logger.risk(f"Trade rejected: {reason}", symbol=symbol, signal=signal)
        return

    sl, tp = sig.sl_tp(signal, price, atr)

    # Execute order
    exchange_side = "buy" if signal == "long" else "sell"
    order = await ex.place_order(symbol, exchange_side, size, price)
    fill_price = order["price"]
    fill_size  = order["filled"]

    # Recompute SL/TP from actual fill price
    sl, tp = sig.sl_tp(signal, fill_price, atr)

    pos_id = await db.open_position(symbol, signal, fill_price, fill_size, sl, tp)

    risk.record_signal(symbol)

    logger.trade(
        "OPEN",
        symbol=symbol,
        side=signal,
        price=fill_price,
        size=round(fill_size, 6),
        sl=round(sl, 4),
        tp=round(tp, 4),
        atr=round(atr, 4),
        equity=round(equity, 2),
        id=pos_id,
    )

    # Daily loss check — halt if breach after this trade
    new_daily = await db.get_daily_pnl()
    loss_limit = equity * CFG.max_daily_loss
    if new_daily <= -abs(loss_limit):
        logger.risk("Daily loss limit hit — halting for today")
        await db.set_halted()


# ── Main loop ─────────────────────────────────────────────────────────────────

async def main() -> None:
    CFG.validate()
    os.makedirs("data", exist_ok=True)
    await db.init_db()

    ex      = build_exchange()
    health_runner = await health.start_health_server()

    logger.info("=" * 60)
    logger.info(f"TradeBot started | mode={CFG.mode} | symbols={CFG.symbols}")
    logger.info(f"Capital={CFG.capital} | risk/trade={CFG.risk_per_trade:.1%} "
                f"| max_daily_loss={CFG.max_daily_loss:.1%}")
    logger.info(f"Kill-switch: touch {CFG.kill_file} to halt")
    logger.info("=" * 60)

    try:
        while not _shutdown.is_set():
            # Kill-switch check
            if risk.kill_switch_active():
                logger.risk("Kill switch file present — bot suspended. Remove to resume.")
                await asyncio.sleep(CFG.poll_interval)
                continue

            # Check open position exits
            try:
                await check_exits(ex)
            except Exception as e:
                logger.error("check_exits error", err=str(e))

            # Entry scan per symbol
            for symbol in CFG.symbols:
                if _shutdown.is_set():
                    break
                try:
                    await try_entry(ex, symbol)
                except Exception as e:
                    logger.error("try_entry error", symbol=symbol, err=str(e))

            # Summary log every tick
            open_pos  = await db.get_open_positions()
            daily_pnl = await db.get_daily_pnl()
            logger.info(
                "tick",
                equity=round(ex.equity, 2),
                open_positions=len(open_pos),
                daily_pnl=round(daily_pnl, 4),
            )

            try:
                await asyncio.wait_for(_shutdown.wait(), timeout=CFG.poll_interval)
            except asyncio.TimeoutError:
                pass

    finally:
        logger.info("Shutting down...")
        # Close any remaining open positions at last known price (paper only)
        if CFG.mode == "paper":
            open_pos = await db.get_open_positions()
            for pos in open_pos:
                ticker = await ex.fetch_ticker(pos["symbol"])
                price  = ticker["last"]
                if price > 0:
                    pnl = await db.close_position(pos["id"], price, "shutdown")
                    logger.trade("CLOSE", symbol=pos["symbol"], reason="shutdown",
                                 exit=price, pnl=round(pnl, 4))

        await ex.close()
        await health_runner.cleanup()
        logger.info("Bot stopped cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
