"""logger.py — Structured JSON-lines trade log + console output"""
import json
import sys
import os
from datetime import datetime, timezone
from config import CFG


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def _write(record: dict) -> None:
    os.makedirs(os.path.dirname(CFG.log_path), exist_ok=True)
    with open(CFG.log_path, "a") as f:
        f.write(json.dumps(record) + "\n")


def _console(level: str, msg: str, extra: dict = None) -> None:
    tag = {"INFO": "·", "WARN": "⚠", "ERROR": "✖", "TRADE": "🔁", "RISK": "🛑"}.get(level, "?")
    ts = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%H:%M:%S")
    suffix = "  " + json.dumps(extra) if extra else ""
    print(f"[{ts}] {tag} {msg}{suffix}", flush=True)


def info(msg: str, **kw) -> None:
    _console("INFO", msg, kw or None)
    _write({"ts": _now(), "level": "INFO", "msg": msg, **kw})


def warn(msg: str, **kw) -> None:
    _console("WARN", msg, kw or None)
    _write({"ts": _now(), "level": "WARN", "msg": msg, **kw})


def error(msg: str, **kw) -> None:
    _console("ERROR", msg, kw or None)
    _write({"ts": _now(), "level": "ERROR", "msg": msg, **kw})


def trade(event: str, **kw) -> None:
    """Log a trade event (OPEN, CLOSE, REJECT, HALT)."""
    _console("TRADE", f"[{event}] " + " ".join(f"{k}={v}" for k, v in kw.items()))
    _write({"ts": _now(), "level": "TRADE", "event": event, **kw})


def risk(msg: str, **kw) -> None:
    _console("RISK", msg, kw or None)
    _write({"ts": _now(), "level": "RISK", "msg": msg, **kw})
