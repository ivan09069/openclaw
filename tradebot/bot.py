"""bot.py — Main trading loop

Flow per tick:
  1. Kill-switch check
  2. Reconcile open positions from DB on startup
  3. Check exits on all open positions
  4. For each symbol: fetch OHLCV → signal → spread check → risk gate → execute
  5. Persist state on shutdown

Run:
  python bot.py
"""

import asyncio
import signal
import os
from datetime import datetime, timezone

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
    logger.info(f"Signal {signum} received — shutting down gracefully")
    _shutdown.set()


signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ── Startup reconciliation ────────────────────────────────────────────────────

async def reconcile_positions(ex) -> None:
    """
    On startup, log all positions currently marked 'open' in the DB.
    In paper mode we leave them as-is (they'll be monitored normally).
    In live/testnet mode, emit a warning for each so the operator can verify
    they exist on the exchange — we do NOT auto-cancel or auto-close them.
    """
    open_pos = await db.get_open_positions()
    if not open_pos:
        logger.info("reconcile: no open positions in DB")
        return

    logger.info(f"reconcile: found {len(open_pos)} open position(s) in DB")
    for p in open_pos:
        logger.info(
            "reconcile: open position",
            id=p["id"],
            symbol=p["symbol"],
            side=p["side"],
            entry=p["entry_price"],
            size=p["size"],
            sl=p["sl"],
            tp=p["tp"],
            opened_at=p["opened_at"],
        )
        if CFG.mode in ("live", "testnet"):
            logger.warn(
                "reconcile: VERIFY this position exists on exchange before continuing",
                symbol=p["symbol"],
                id=p["id"],
            )


# ── Exit management ───────────────────────────────────────────────────────────

async def check_exits(ex) -> None:
    """Scan open positions; close those that have hit SL or TP."""
    open_pos = await db.get_open_positions()
    for pos in open_pos:
        ticker = await ex.fetch_ticker(pos["symbol"])
        price  = ticker["last"]
        if price <= 0:
            logger.warn(
                "check_exits: zero price returned — skipping",
                symbol=pos["symbol"],
            )
            continue

        should_exit, reason = risk.should_exit(pos, price)
        if should_exit:
            pnl = await db.close_position(pos["id"], price, reason)
            logger.trade(
                "CLOSE",
                symbol=pos["symbol"],
                side=pos["side"],
                entry=pos["entry_price"],
                exit=round(price, 4),
                pnl=round(pnl, 4),
                reason=reason,
                id=pos["id"],
            )
            if CFG.mode == "paper":
                ex.equity += pnl


# ── Entry logic ───────────────────────────────────────────────────────────────

async def try_entry(ex, symbol: str) -> None:
    """Fetch candles → signal → risk gate → execute entry."""

    ohlcv = await ex.fetch_ohlcv(symbol, CFG.timeframe, CFG.ohlcv_limit)
    if not ohlcv:
        logger.warn("try_entry: no OHLCV data — skipping", symbol=symbol)
        return

    result = sig.compute(ohlcv)
    signal  = result["signal"]
    price   = result["price"]
    atr     = result["atr"]

    # Stale data is already forced to "flat" inside signals.py,
    # but log it explicitly here too so the operator can see it.
    if result.get("stale"):
        logger.warn(
            "try_entry: stale candles — no entry",
            symbol=symbol,
            age_s=result.get("candle_age_s"),
        )
        return

    if signal == "flat":
        return

    logger.info(
        f"Signal {signal.upper()} {symbol}",
        rsi=result["rsi"],
        ema_fast=result["ema_fast"],
        ema_slow=result["ema_slow"],
        atr=round(atr, 4),
        candle_age_s=result.get("candle_age_s"),
    )

    equity = ex.equity
    size   = risk.position_size(price, atr, equity)
    if size <= 0:
        return

    # Fetch ticker for spread check
    ticker = await ex.fetch_ticker(symbol)
    if ticker["last"] <= 0:
        logger.warn("try_entry: ticker returned zero price — aborting", symbol=symbol)
        return

    open_pos  = await db.get_open_positions()
    daily_pnl = await db.get_daily_pnl()
    halted    = await db.is_halted()

    allowed, reason = risk.can_trade(
        symbol, signal, open_pos, equity, daily_pnl, halted,
        size, price,
        ticker=ticker,
        atr=atr,
    )
    if not allowed:
        logger.risk(f"Trade rejected: {reason}", symbol=symbol, signal=signal)
        return

    sl, tp = sig.sl_tp(signal, price, atr)

    exchange_side = "buy" if signal == "long" else "sell"
    try:
        order = await ex.place_order(symbol, exchange_side, size, price)
    except Exception as e:
        logger.error(
            "try_entry: order failed — position NOT opened",
            symbol=symbol, err=str(e)[:200],
        )
        return

    fill_price = order["price"]
    fill_size  = order["filled"]

    # Recompute SL/TP from actual fill
    sl, tp = sig.sl_tp(signal, fill_price, atr)

    pos_id = await db.open_position(
        symbol, signal, fill_price, fill_size, sl, tp,
        atr_entry=round(atr, 4),
        rsi_entry=result["rsi"],
        ema_fast_entry=result["ema_fast"],
        ema_slow_entry=result["ema_slow"],
        reason_entered="ema_cross_rsi",
    )

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
        rsi=result["rsi"],
        equity=round(equity, 2),
        id=pos_id,
    )

    # Post-trade daily loss check
    new_daily  = await db.get_daily_pnl()
    loss_limit = equity * CFG.max_daily_loss
    if new_daily <= -abs(loss_limit):
        logger.risk("Daily loss limit hit — halting trading for today")
        await db.set_halted()


# ── Main loop ─────────────────────────────────────────────────────────────────

async def main() -> None:
    CFG.validate()
    os.makedirs("data", exist_ok=True)
    await db.init_db()

    ex = build_exchange()

    # ── Readiness check ───────────────────────────────────────────────────────
    ready_ok, ready_reason = await ex.readiness_check()
    if not ready_ok:
        logger.error(f"STARTUP ABORTED — readiness check failed: {ready_reason}")
        await ex.close()
        return

    # ── Register exchange with health module ──────────────────────────────────
    health.register_exchange(ex)
    health_runner = await health.start_health_server()

    # ── Rich startup block ────────────────────────────────────────────────────
    open_pos   = await db.get_open_positions()
    daily_pnl  = await db.get_daily_pnl()
    halted     = await db.is_halted()
    kill_state = risk.kill_switch_active()

    logger.info("=" * 64)
    logger.info(f"TradeBot starting")
    logger.info(f"  mode         : {CFG.mode}")
    logger.info(f"  exchange     : {CFG.exchange}")
    logger.info(f"  symbols      : {CFG.symbols}")
    logger.info(f"  timeframe    : {CFG.timeframe}  poll={CFG.poll_interval}s")
    logger.info(f"  equity       : {ex.equity:.2f} USD")
    logger.info(f"  risk/trade   : {CFG.risk_per_trade:.1%}")
    logger.info(f"  max_daily_loss: {CFG.max_daily_loss:.1%}")
    logger.info(f"  max_exposure : {CFG.max_exposure:.1%}  max_pos={CFG.max_positions}")
    logger.info(f"  spread_limit : {CFG.max_spread_pct:.3%}")
    logger.info(f"  stale_cutoff : {CFG.candle_stale_seconds}s")
    logger.info(f"  daily_pnl    : {daily_pnl:.4f}")
    logger.info(f"  open_pos     : {len(open_pos)}")
    logger.info(f"  halted       : {halted}")
    logger.info(f"  kill_switch  : {kill_state}")
    logger.info(f"  kill_file    : {CFG.kill_file}")
    logger.info("=" * 64)

    # ── Reconcile existing positions ──────────────────────────────────────────
    await reconcile_positions(ex)

    try:
        while not _shutdown.is_set():

            if risk.kill_switch_active():
                logger.risk("Kill switch active — bot suspended. Remove file to resume.")
                try:
                    await asyncio.wait_for(_shutdown.wait(), timeout=CFG.poll_interval)
                except asyncio.TimeoutError:
                    pass
                continue

            # Exit scan
            try:
                await check_exits(ex)
            except Exception as e:
                logger.error("check_exits error", err=str(e))

            # Entry scan
            for symbol in CFG.symbols:
                if _shutdown.is_set():
                    break
                try:
                    await try_entry(ex, symbol)
                except Exception as e:
                    logger.error("try_entry error", symbol=symbol, err=str(e))

            # Tick summary
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
        logger.info("Shutdown initiated — persisting state...")

        # Persist equity for resume
        await db.set_state("last_equity",  ex.equity)
        await db.set_state("stopped_at",   datetime.now(timezone.utc).replace(tzinfo=None).isoformat())
        await db.set_state("last_mode",    CFG.mode)

        # Paper: close residual open positions at last known price
        if CFG.mode == "paper":
            open_pos = await db.get_open_positions()
            if open_pos:
                logger.info(f"Closing {len(open_pos)} paper position(s) at market...")
            for pos in open_pos:
                ticker = await ex.fetch_ticker(pos["symbol"])
                price  = ticker["last"]
                if price > 0:
                    pnl = await db.close_position(pos["id"], price, "shutdown")
                    logger.trade(
                        "CLOSE",
                        symbol=pos["symbol"],
                        reason="shutdown",
                        exit=round(price, 4),
                        pnl=round(pnl, 4),
                    )

        await ex.close()
        await health_runner.cleanup()
        logger.info("Bot stopped cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
