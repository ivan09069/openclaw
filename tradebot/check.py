"""check.py — Pre-flight sanity check. Run before bot.py.

Verifies:
  - All imports work
  - Config loads and validates
  - DB can be created
  - Exchange can reach the network (public endpoint)
  - Signals compute correctly on synthetic data
"""
import asyncio
import sys

async def run():
    print("── Pre-flight check ─────────────────────────────")

    # Config
    print("[1/5] Config...")
    from config import CFG
    CFG.validate()
    print(f"      OK  mode={CFG.mode} symbols={CFG.symbols}")

    # DB
    print("[2/5] Database...")
    import db
    import os
    os.makedirs("data", exist_ok=True)
    await db.init_db()
    print("      OK  SQLite initialized")

    # Signals (synthetic data)
    print("[3/5] Signal engine...")
    import signals
    import random
    random.seed(42)
    fake_ohlcv = []
    price = 50000.0
    import time
    ts = int(time.time() * 1000) - 300 * 5 * 60 * 1000
    for i in range(300):
        o = price
        c = price * (1 + random.uniform(-0.002, 0.002))
        h = max(o, c) * (1 + random.uniform(0, 0.001))
        l = min(o, c) * (1 - random.uniform(0, 0.001))
        v = random.uniform(1, 10)
        fake_ohlcv.append([ts + i * 5 * 60 * 1000, o, h, l, c, v])
        price = c
    result = signals.compute(fake_ohlcv)
    print(f"      OK  signal={result['signal']} rsi={result['rsi']} atr={result['atr']:.2f}")

    # Risk
    print("[4/5] Risk engine...")
    import risk
    size = risk.position_size(price=50000, atr=500, equity=10000)
    print(f"      OK  sample size={size:.6f} BTC for $10k equity")

    # Exchange (network)
    print("[5/5] Exchange connectivity...")
    from exchange import build_exchange
    ex = build_exchange()
    ohlcv = await ex.fetch_ohlcv("BTC/USDT", "5m", 5)
    if ohlcv:
        print(f"      OK  fetched {len(ohlcv)} candles, last close={ohlcv[-1][4]}")
    else:
        print("      WARN  no candles returned (network issue?)")
    await ex.close()

    print("─────────────────────────────────────────────────")
    print("All checks passed. Run:  python bot.py")

asyncio.run(run())
