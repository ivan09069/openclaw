"""config.py — Load and validate all settings from .env"""
import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()


def _float(key: str, default: float) -> float:
    return float(os.getenv(key, default))


def _int(key: str, default: int) -> int:
    return int(os.getenv(key, default))


def _str(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).strip().lower() in ("1", "true", "yes")


@dataclass
class Config:
    exchange: str = field(default_factory=lambda: _str("EXCHANGE", "kraken"))
    api_key: str = field(default_factory=lambda: _str("API_KEY"))
    api_secret: str = field(default_factory=lambda: _str("API_SECRET"))
    mode: str = field(default_factory=lambda: _str("MODE", "paper").lower())

    symbols: List[str] = field(
        default_factory=lambda: [s.strip() for s in _str("SYMBOLS", "BTC/USD").split(",")]
    )

    capital: float = field(default_factory=lambda: _float("CAPITAL", 10000))
    risk_per_trade: float = field(default_factory=lambda: _float("RISK_PER_TRADE", 0.01))
    max_daily_loss: float = field(default_factory=lambda: _float("MAX_DAILY_LOSS", 0.02))
    max_exposure: float = field(default_factory=lambda: _float("MAX_EXPOSURE", 0.20))
    max_positions: int = field(default_factory=lambda: _int("MAX_POSITIONS", 3))
    cooldown_seconds: int = field(default_factory=lambda: _int("COOLDOWN_SECONDS", 300))

    ema_fast: int = field(default_factory=lambda: _int("EMA_FAST", 9))
    ema_slow: int = field(default_factory=lambda: _int("EMA_SLOW", 21))
    rsi_period: int = field(default_factory=lambda: _int("RSI_PERIOD", 14))
    rsi_long_threshold: float = field(default_factory=lambda: _float("RSI_LONG_THRESHOLD", 55))
    rsi_short_threshold: float = field(default_factory=lambda: _float("RSI_SHORT_THRESHOLD", 45))
    atr_period: int = field(default_factory=lambda: _int("ATR_PERIOD", 14))
    atr_sl_mult: float = field(default_factory=lambda: _float("ATR_SL_MULT", 2.0))
    atr_tp_mult: float = field(default_factory=lambda: _float("ATR_TP_MULT", 3.0))

    timeframe: str = field(default_factory=lambda: _str("TIMEFRAME", "5m"))
    poll_interval: int = field(default_factory=lambda: _int("POLL_INTERVAL", 30))
    ohlcv_limit: int = field(default_factory=lambda: _int("OHLCV_LIMIT", 200))

    # ── Staleness / slippage guards ─────────────────────────────────────────
    # How old the last candle can be before we refuse to trade (seconds).
    # For a 5m timeframe, 2 closed candles = 600s is a reasonable ceiling.
    candle_stale_seconds: int = field(
        default_factory=lambda: _int("CANDLE_STALE_SECONDS", 600)
    )
    # Max allowed (ask-bid)/mid spread as a fraction.  0.005 = 0.5 %.
    max_spread_pct: float = field(
        default_factory=lambda: _float("MAX_SPREAD_PCT", 0.005)
    )

    # ── Paper → live gate ───────────────────────────────────────────────────
    # Minimum number of *closed* paper trades before live mode is allowed.
    min_paper_trades_for_live: int = field(
        default_factory=lambda: _int("MIN_PAPER_TRADES_FOR_LIVE", 20)
    )
    # Must be explicitly set to true in .env to unlock live mode.
    live_acknowledged: bool = field(
        default_factory=lambda: _bool("LIVE_ACKNOWLEDGED", False)
    )

    db_path: str = field(default_factory=lambda: _str("DB_PATH", "data/tradebot.db"))
    log_path: str = field(default_factory=lambda: _str("LOG_PATH", "data/trades.jsonl"))
    health_port: int = field(default_factory=lambda: _int("HEALTH_PORT", 8765))
    kill_file: str = field(default_factory=lambda: _str("KILL_FILE", "data/KILL"))

    def validate(self) -> None:
        assert self.mode in ("paper", "testnet", "live"), f"Invalid MODE: {self.mode}"
        assert 0 < self.risk_per_trade <= 0.05, "RISK_PER_TRADE must be 0–5%"
        assert 0 < self.max_daily_loss <= 0.10, "MAX_DAILY_LOSS must be 0–10%"
        assert 0 < self.max_exposure <= 1.0, "MAX_EXPOSURE must be 0–100%"
        assert self.max_positions >= 1
        assert self.candle_stale_seconds > 0
        assert 0 < self.max_spread_pct < 0.10, "MAX_SPREAD_PCT must be < 10%"
        if self.mode == "live":
            assert self.api_key and self.api_secret, \
                "API_KEY and API_SECRET required for live mode"
        print(
            f"[config] mode={self.mode} capital={self.capital} "
            f"symbols={self.symbols} exchange={self.exchange}"
        )


CFG = Config()
