"""health.py — HTTP health, metrics, readiness, and kill endpoints

Routes:
  GET /health   — liveness: status, mode, uptime, daily PnL, kill/halt state
  GET /metrics  — full operator dashboard (unrealized PnL, exposure, cooldowns…)
  GET /ready    — readiness: fails if exchange or config validation is broken
  GET /kill     — write KILL file (emergency stop)
  GET /unkill   — remove KILL file (resume)
"""

import json
import os
from aiohttp import web
from datetime import datetime, timezone
from config import CFG
import db
import risk
import logger

_start_time  = datetime.now(timezone.utc).replace(tzinfo=None)
_exchange_ref = None   # set by bot.py after exchange is built


def register_exchange(ex) -> None:
    """Called by bot.py so health endpoints can inspect live equity/positions."""
    global _exchange_ref
    _exchange_ref = ex


def _uptime_s() -> int:
    return int((datetime.now(timezone.utc).replace(tzinfo=None) - _start_time).total_seconds())


def _unrealized_pnl(open_pos: list, prices: dict) -> float:
    total = 0.0
    for p in open_pos:
        price = prices.get(p["symbol"], 0.0)
        if price <= 0:
            continue
        if p["side"] == "long":
            total += (price - p["entry_price"]) * p["size"]
        else:
            total += (p["entry_price"] - price) * p["size"]
    return round(total, 4)


def _exposure_used(open_pos: list, equity: float) -> float:
    if equity <= 0:
        return 0.0
    notional = sum(p["size"] * p["entry_price"] for p in open_pos)
    return round(notional / equity, 4)


# ── Handlers ─────────────────────────────────────────────────────────────────

async def _health(request):
    open_pos  = await db.get_open_positions()
    daily_pnl = await db.get_daily_pnl()
    halted    = await db.is_halted()
    kill      = os.path.exists(CFG.kill_file)
    uptime    = _uptime_s()

    ok     = not (halted or kill)
    status = "OK" if ok else ("KILLED" if kill else "HALTED")

    payload = {
        "status":        status,
        "mode":          CFG.mode,
        "exchange":      CFG.exchange,
        "uptime_s":      uptime,
        "open_positions": len(open_pos),
        "daily_pnl_usd": round(daily_pnl, 4),
        "kill_switch":   kill,
        "halted":        halted,
        "ts":            datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
    }
    http_status = 200 if ok else 503
    return web.Response(
        text=json.dumps(payload, indent=2),
        content_type="application/json",
        status=http_status,
    )


async def _metrics(request):
    open_pos        = await db.get_open_positions()
    daily_pnl       = await db.get_daily_pnl()
    today_trades    = await db.get_today_trade_count()
    halted          = await db.is_halted()
    kill            = os.path.exists(CFG.kill_file)
    cooldowns       = risk.cooldown_state()

    equity = _exchange_ref.equity if _exchange_ref else CFG.capital

    # Best-effort unrealized PnL (skip if exchange is down)
    prices: dict = {}
    if _exchange_ref:
        for pos in open_pos:
            sym = pos["symbol"]
            if sym not in prices:
                try:
                    t = await _exchange_ref.fetch_ticker(sym)
                    prices[sym] = t.get("last", 0.0)
                except Exception:
                    prices[sym] = 0.0

    unreal_pnl = _unrealized_pnl(open_pos, prices)
    exposure   = _exposure_used(open_pos, equity)

    payload = {
        "ts":             datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
        "uptime_s":       _uptime_s(),
        "mode":           CFG.mode,
        "exchange":       CFG.exchange,
        "bot_status":     "HALTED" if halted else ("KILLED" if kill else "RUNNING"),
        "equity_usd":     round(equity, 2),
        # Today
        "trades_today":   today_trades,
        "realized_pnl_today_usd": round(daily_pnl, 4),
        "unrealized_pnl_usd":     unreal_pnl,
        # Risk state
        "exposure_used":  exposure,
        "exposure_cap":   CFG.max_exposure,
        "kill_switch":    kill,
        "daily_halt":     halted,
        "cooldowns_s":    cooldowns,
        # Positions
        "open_positions": [
            {
                "id":     p["id"],
                "symbol": p["symbol"],
                "side":   p["side"],
                "entry":  p["entry_price"],
                "size":   p["size"],
                "sl":     p["sl"],
                "tp":     p["tp"],
                "unreal_pnl": round(
                    (prices.get(p["symbol"], 0) - p["entry_price"]) * p["size"]
                    if p["side"] == "long"
                    else (p["entry_price"] - prices.get(p["symbol"], 0)) * p["size"],
                    4,
                ),
            }
            for p in open_pos
        ],
    }
    return web.Response(
        text=json.dumps(payload, indent=2),
        content_type="application/json",
    )


async def _ready(request):
    """
    Readiness check.  Returns 200 only when:
      - config validates
      - exchange connectivity confirmed
    Used by monitoring / load balancers.
    """
    errors = []

    # Config validation
    try:
        CFG.validate()
    except Exception as e:
        errors.append(f"config: {e}")

    # Exchange connectivity
    if _exchange_ref:
        ok, reason = await _exchange_ref.readiness_check()
        if not ok:
            errors.append(f"exchange: {reason}")
    else:
        errors.append("exchange not initialised yet")

    if errors:
        return web.Response(
            text=json.dumps({"ready": False, "errors": errors}, indent=2),
            content_type="application/json",
            status=503,
        )
    return web.Response(
        text=json.dumps({"ready": True}, indent=2),
        content_type="application/json",
        status=200,
    )


async def _kill(request):
    os.makedirs(os.path.dirname(CFG.kill_file) or ".", exist_ok=True)
    open(CFG.kill_file, "w").close()
    logger.risk("KILL SWITCH ACTIVATED via HTTP endpoint")
    return web.Response(
        text=json.dumps({"status": "killed", "ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"}),
        content_type="application/json",
    )


async def _unkill(request):
    if os.path.exists(CFG.kill_file):
        os.remove(CFG.kill_file)
        logger.info("Kill switch cleared via HTTP endpoint")
    return web.Response(
        text=json.dumps({"status": "resumed", "ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"}),
        content_type="application/json",
    )


# ── Server setup ──────────────────────────────────────────────────────────────

async def start_health_server():
    app = web.Application()
    app.router.add_get("/health",  _health)
    app.router.add_get("/metrics", _metrics)
    app.router.add_get("/ready",   _ready)
    app.router.add_get("/kill",    _kill)
    app.router.add_get("/unkill",  _unkill)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", CFG.health_port)
    await site.start()
    logger.info(f"Health server  http://0.0.0.0:{CFG.health_port}  "
                f"[/health /metrics /ready /kill /unkill]")
    return runner
