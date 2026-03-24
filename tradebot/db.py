"""db.py — SQLite persistence via aiosqlite"""
import aiosqlite
import json
from datetime import datetime
from config import CFG

DB = CFG.db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT    NOT NULL,
    side        TEXT    NOT NULL,  -- 'long' | 'short'
    entry_price REAL    NOT NULL,
    size        REAL    NOT NULL,  -- base units
    sl          REAL    NOT NULL,
    tp          REAL    NOT NULL,
    opened_at   TEXT    NOT NULL,
    status      TEXT    DEFAULT 'open',  -- 'open' | 'closed'
    closed_at   TEXT,
    close_price REAL,
    pnl         REAL,
    close_reason TEXT
);

CREATE TABLE IF NOT EXISTS daily_stats (
    date        TEXT    PRIMARY KEY,
    realized_pnl REAL   DEFAULT 0,
    trades_won  INTEGER DEFAULT 0,
    trades_lost INTEGER DEFAULT 0,
    halted      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bot_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB) as conn:
        await conn.executescript(SCHEMA)
        await conn.commit()


async def open_position(symbol, side, entry, size, sl, tp) -> int:
    async with aiosqlite.connect(DB) as conn:
        cur = await conn.execute(
            """INSERT INTO positions (symbol,side,entry_price,size,sl,tp,opened_at)
               VALUES (?,?,?,?,?,?,?)""",
            (symbol, side, entry, size, sl, tp, datetime.utcnow().isoformat()),
        )
        await conn.commit()
        return cur.lastrowid


async def close_position(pos_id: int, close_price: float, reason: str) -> float:
    async with aiosqlite.connect(DB) as conn:
        row = await (await conn.execute(
            "SELECT side,entry_price,size FROM positions WHERE id=?", (pos_id,)
        )).fetchone()
        if not row:
            return 0.0
        side, entry, size = row
        pnl = (close_price - entry) * size if side == "long" else (entry - close_price) * size
        await conn.execute(
            """UPDATE positions SET status='closed',closed_at=?,close_price=?,pnl=?,close_reason=?
               WHERE id=?""",
            (datetime.utcnow().isoformat(), close_price, pnl, reason, pos_id),
        )
        # update daily stats
        today = datetime.utcnow().date().isoformat()
        await conn.execute(
            """INSERT INTO daily_stats (date,realized_pnl,trades_won,trades_lost)
               VALUES (?,?,?,?)
               ON CONFLICT(date) DO UPDATE SET
                 realized_pnl = realized_pnl + excluded.realized_pnl,
                 trades_won   = trades_won + excluded.trades_won,
                 trades_lost  = trades_lost + excluded.trades_lost""",
            (today, pnl, 1 if pnl >= 0 else 0, 0 if pnl >= 0 else 1),
        )
        await conn.commit()
        return pnl


async def get_open_positions() -> list:
    async with aiosqlite.connect(DB) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT * FROM positions WHERE status='open'"
        )).fetchall()
        return [dict(r) for r in rows]


async def get_daily_pnl(date: str = None) -> float:
    date = date or datetime.utcnow().date().isoformat()
    async with aiosqlite.connect(DB) as conn:
        row = await (await conn.execute(
            "SELECT realized_pnl FROM daily_stats WHERE date=?", (date,)
        )).fetchone()
        return row[0] if row else 0.0


async def is_halted(date: str = None) -> bool:
    date = date or datetime.utcnow().date().isoformat()
    async with aiosqlite.connect(DB) as conn:
        row = await (await conn.execute(
            "SELECT halted FROM daily_stats WHERE date=?", (date,)
        )).fetchone()
        return bool(row and row[0])


async def set_halted(date: str = None) -> None:
    date = date or datetime.utcnow().date().isoformat()
    async with aiosqlite.connect(DB) as conn:
        await conn.execute(
            """INSERT INTO daily_stats (date,halted) VALUES (?,1)
               ON CONFLICT(date) DO UPDATE SET halted=1""",
            (date,),
        )
        await conn.commit()


async def get_state(key: str, default=None):
    async with aiosqlite.connect(DB) as conn:
        row = await (await conn.execute(
            "SELECT value FROM bot_state WHERE key=?", (key,)
        )).fetchone()
        return json.loads(row[0]) if row else default


async def set_state(key: str, value) -> None:
    async with aiosqlite.connect(DB) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO bot_state (key,value) VALUES (?,?)",
            (key, json.dumps(value)),
        )
        await conn.commit()
