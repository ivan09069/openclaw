# TradeBot 🦞

Paper-first crypto trading bot. EMA crossover + RSI filter + ATR sizing.

## File map

```
tradebot/
├── .env.example    ← copy to .env, fill in values
├── config.py       ← all settings from env
├── db.py           ← SQLite persistence
├── logger.py       ← structured JSON-lines log
├── signals.py      ← EMA9/21 crossover + RSI14 + ATR14
├── risk.py         ← sizing, exposure, daily loss, cooldown, kill-switch
├── exchange.py     ← paper / testnet / live abstraction
├── health.py       ← HTTP health + kill endpoints
├── bot.py          ← main loop
├── check.py        ← pre-flight sanity check
└── data/
    ├── tradebot.db  ← SQLite (positions, daily stats)
    ├── trades.jsonl ← append-only trade log
    └── KILL         ← touch to halt; rm to resume
```

## Setup

```bash
# Install deps (once)
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env — no secrets needed for paper mode

# Pre-flight check
python check.py

# Run
python bot.py
```

## Kill-switch

```bash
# Halt immediately (no new trades, open positions stay open until SL/TP)
touch data/KILL

# Or via HTTP
curl http://localhost:8765/kill

# Resume
rm data/KILL
curl http://localhost:8765/unkill
```

## Health check

```bash
curl http://localhost:8765/health   # status + daily PnL
curl http://localhost:8765/metrics  # open positions detail
```

## Modes

| MODE     | API Keys | Orders    |
|----------|----------|-----------|
| paper    | no       | simulated |
| testnet  | yes*     | Binance sandbox |
| live     | yes      | real money ⚠️ |

*Binance testnet keys from https://testnet.binance.vision

## Risk controls (defaults)

| Control | Default |
|---------|---------|
| Risk per trade | 1% of equity |
| Max daily loss | 2% → halts for the day |
| Max exposure | 20% of capital |
| Max concurrent positions | 3 |
| Cooldown per symbol | 300s |
| Stop-loss | Entry ± ATR × 2 |
| Take-profit | Entry ± ATR × 3 |

All configurable via `.env`.
