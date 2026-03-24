"""health.py — Lightweight HTTP health endpoint

GET http://localhost:8765/health  →  JSON status summary
GET http://localhost:8765/metrics →  open positions + daily PnL
GET http://localhost:8765/kill    →  creates KILL file (emergency stop)
GET http://localhost:8765/unkill  →  removes KILL file (resume)
"""

import json
import os
from aiohttp import web
from datetime import datetime
from config import CFG
import db
import logger

_start_time = datetime.utcnow()


async def _health(request):
    open_pos = await db.get_open_positions()
    daily_pnl = await db.get_daily_pnl()
    halted = await db.is_halted()
    kill = os.path.exists(CFG.kill_file)
    uptime = int((datetime.utcnow() - _start_time).total_seconds())

    payload = {
        "status": "HALTED" if (halted or kill) else "OK",
        "mode": CFG.mode,
        "uptime_s": uptime,
        "open_positions": len(open_pos),
        "daily_pnl_usd": round(daily_pnl, 4),
        "kill_switch": kill,
        "halted": halted,
        "ts": datetime.utcnow().isoformat() + "Z",
    }
    status = 200 if payload["status"] == "OK" else 503
    return web.Response(text=json.dumps(payload, indent=2),
                        content_type="application/json", status=status)


async def _metrics(request):
    open_pos = await db.get_open_positions()
    daily_pnl = await db.get_daily_pnl()
    return web.Response(
        text=json.dumps({
            "daily_pnl_usd": round(daily_pnl, 4),
            "open_positions": open_pos,
        }, indent=2),
        content_type="application/json"
    )


async def _kill(request):
    os.makedirs(os.path.dirname(CFG.kill_file), exist_ok=True)
    open(CFG.kill_file, "w").close()
    logger.risk("KILL SWITCH ACTIVATED via HTTP")
    return web.Response(text='{"status":"killed"}', content_type="application/json")


async def _unkill(request):
    if os.path.exists(CFG.kill_file):
        os.remove(CFG.kill_file)
        logger.info("Kill switch cleared via HTTP")
    return web.Response(text='{"status":"resumed"}', content_type="application/json")


async def start_health_server():
    app = web.Application()
    app.router.add_get("/health",  _health)
    app.router.add_get("/metrics", _metrics)
    app.router.add_get("/kill",    _kill)
    app.router.add_get("/unkill",  _unkill)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", CFG.health_port)
    await site.start()
    logger.info(f"Health server running on http://0.0.0.0:{CFG.health_port}")
    return runner
