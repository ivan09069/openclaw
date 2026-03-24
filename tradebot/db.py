"""db.py — SQLite persistence via aiosqlite

Schema v2 additions (auto-migrated):
  positions: atr_entry, rsi_entry, ema_fast_entry, ema_slow_entry,
             fees, r_multiple, duration_s, reason_entered
"""
import aiosqlite
import json
from datetime import datetime, timezone
from config import CFG

DB = CFG.db_path

# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
_BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol           TEXT    NOT NULL,
    side             TEXT    NOT NULL,
    entry_price      REAL    NOT NULL,
    size             REAL    NOT NULL,
    sl               REAL    NOT NULL,
    tp               REAL    NOT NULL,
    opened_at        TEXT    NOT NULL,
    status           TEXT    DEFAULT 'open',
    closed_at        TEXT,
    close_price      REAL,
    pnl              REAL,
    close_reason     TEXT,
    -- v2 journal columns (NULL-safe for old rows)
    atr_entry        REAL,
    rsi_entry        REAL,
    ema_fast_entry   REAL,
    ema_slow_entry   REAL,
    fees             REAL    DEFAULT 0,
    r_multiple       REAL,
    duration_s       REAL,
    reason_entered   TEXT
);

CREATE TABLE IF NOT EXISTS daily_stats (
    date         TEXT    PRIMARY KEY,
    realized_pnl REAL    DEFAULT 0,
    trades_won   INTEGER DEFAULT 0,
    trades_lost  INTEGER DEFAULT 0,
    halted       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bot_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# Columns added in v2 — safe to re-run (will fail silently if column exists)
_MIGRATIONS = [
    "ALTER TABLE positions ADD COLUMN atr_entry      REAL",
    "ALTER TABLE positions ADD COLUMN rsi_entry      REAL",
    "ALTER TABLE positions ADD COLUMN ema_fast_entry REAL",
    "ALTER TABLE positions ADD COLUMN ema_slow_entry REAL",
    "ALTER TABLE positions ADD COLUMN fees           REAL DEFAULT 0",
    "ALTER TABLE positions ADD COLUMN r_multiple     REAL",
    "ALTER TABLE positions ADD COLUMN duration_s     REAL",
    "ALTER TABLE positions ADD COLUMN reason_entered TEXT",
]


async def init_db() -> None:
    async with aiosqlite.connect(DB) as conn:
        await conn.executescript(_BASE_SCHEMA)
        for sql in _MIGRATIONS:
            try:
                await conn.execute(sql)
            except Exception:
                pass  # column already exists
        await conn.commit()


# --------------------------------------------------------------------------- #
# Positions
# --------------------------------------------------------------------------- #

async def open_position(
    symbol: str,
    side: str,
    entry: float,
    size: float,
    sl: float,
    tp: float,
    *,
    atr_entry: float = 0.0,
    rsi_entry: float = 0.0,
    ema_fast_entry: float = 0.0,
    ema_slow_entry: float = 0.0,
    reason_entered: str = "signal",
) -> int:
    async with aiosqlite.connect(DB) as conn:
        cur = await conn.execute(
            """INSERT INTO positions
               (symbol, side, entry_price, size, sl, tp, opened_at,
                atr_entry, rsi_entry, ema_fast_entry, ema_slow_entry, reason_entered)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                symbol, side, entry, size, sl, tp,
                datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                atr_entry, rsi_entry, ema_fast_entry, ema_slow_entry,
                reason_entered,
            ),
        )
        await conn.commit()
        return cur.lastrowid


async def close_position(pos_id: int, close_price: float, reason: str) -> float:
    async with aiosqlite.connect(DB) as conn:
        row = await (await conn.execute(
            "SELECT side, entry_price, size, sl, opened_at FROM positions WHERE id=?",
            (pos_id,),
        )).fetchone()
        if not row:
            return 0.0

        side, entry, size, sl, opened_at = row
        pnl = (close_price - entry) * size if side == "long" else (entry - close_price) * size

        # R multiple: how many R units did we gain/lose?
        # 1R = entry_price - sl  (for long)
        r_unit = abs(entry - sl) if sl else 0
        r_multiple = (pnl / (r_unit * size)) if (r_unit > 0 and size > 0) else 0.0

        # Duration
        try:
            opened_dt = datetime.fromisoformat(opened_at)
            duration_s = (datetime.now(timezone.utc).replace(tzinfo=None) - opened_dt).total_seconds()
        except Exception:
            duration_s = 0.0

        # Paper fee: 0.1% of notional per leg (0.2% round-trip)
        fees = size * entry * 0.001 + size * close_price * 0.001

        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        await conn.execute(
            """UPDATE positions
               SET status='closed', closed_at=?, close_price=?, pnl=?,
                   close_reason=?, r_multiple=?, duration_s=?, fees=?
               WHERE id=?""",
            (now, close_price, pnl, reason, r_multiple, duration_s, fees, pos_id),
        )

        today = datetime.now(timezone.utc).replace(tzinfo=None).date().isoformat()
        await conn.execute(
            """INSERT INTO daily_stats (date, realized_pnl, trades_won, trades_lost)
               VALUES (?,?,?,?)
               ON CONFLICT(date) DO UPDATE SET
                 realized_pnl = realized_pnl + excluded.realized_pnl,
                 trades_won   = trades_won   + excluded.trades_won,
                 trades_lost  = trades_lost  + excluded.trades_lost""",
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


async def get_closed_count() -> int:
    """Total number of closed (finished) trades across all time."""
    async with aiosqlite.connect(DB) as conn:
        row = await (await conn.execute(
            "SELECT COUNT(*) FROM positions WHERE status='closed'"
        )).fetchone()
        return row[0] if row else 0


async def get_journal(symbol: str = None) -> list:
    """
    Return all closed positions as dicts, optionally filtered by symbol.
    Includes all v2 journal columns.
    """
    async with aiosqlite.connect(DB) as conn:
        conn.row_factory = aiosqlite.Row
        if symbol:
            rows = await (await conn.execute(
                "SELECT * FROM positions WHERE status='closed' AND symbol=? ORDER BY opened_at",
                (symbol,),
            )).fetchall()
        else:
            rows = await (await conn.execute(
                "SELECT * FROM positions WHERE status='closed' ORDER BY opened_at"
            )).fetchall()
        return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Daily stats
# --------------------------------------------------------------------------- #

async def get_daily_pnl(date: str = None) -> float:
    date = date or datetime.now(timezone.utc).replace(tzinfo=None).date().isoformat()
    async with aiosqlite.connect(DB) as conn:
        row = await (await conn.execute(
            "SELECT realized_pnl FROM daily_stats WHERE date=?", (date,)
        )).fetchone()
        return row[0] if row else 0.0


async def get_today_trade_count() -> int:
    today = datetime.now(timezone.utc).replace(tzinfo=None).date().isoformat()
    async with aiosqlite.connect(DB) as conn:
        row = await (await conn.execute(
            "SELECT trades_won + trades_lost FROM daily_stats WHERE date=?", (today,)
        )).fetchone()
        return row[0] if row else 0


async def is_halted(date: str = None) -> bool:
    date = date or datetime.now(timezone.utc).replace(tzinfo=None).date().isoformat()
    async with aiosqlite.connect(DB) as conn:
        row = await (await conn.execute(
            "SELECT halted FROM daily_stats WHERE date=?", (date,)
        )).fetchone()
        return bool(row and row[0])


async def set_halted(date: str = None) -> None:
    date = date or datetime.now(timezone.utc).replace(tzinfo=None).date().isoformat()
    async with aiosqlite.connect(DB) as conn:
        await conn.execute(
            """INSERT INTO daily_stats (date, halted) VALUES (?,1)
               ON CONFLICT(date) DO UPDATE SET halted=1""",
            (date,),
        )
        await conn.commit()


# --------------------------------------------------------------------------- #
# Bot state
# --------------------------------------------------------------------------- #

async def get_state(key: str, default=None):
    async with aiosqlite.connect(DB) as conn:
        row = await (await conn.execute(
            "SELECT value FROM bot_state WHERE key=?", (key,)
        )).fetchone()
        return json.loads(row[0]) if row else default


async def set_state(key: str, value) -> None:
    async with aiosqlite.connect(DB) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO bot_state (key, value) VALUES (?,?)",
            (key, json.dumps(value)),
        )
        await conn.commit()
