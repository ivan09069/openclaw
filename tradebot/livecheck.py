"""livecheck.py — Pre-live gate

Refuses MODE=live unless ALL of the following pass:
  1. LIVE_ACKNOWLEDGED=true in .env
  2. API_KEY and API_SECRET are set
  3. Paper mode has at least MIN_PAPER_TRADES_FOR_LIVE closed trades
  4. Kill-switch is NOT active
  5. Exchange connectivity (readiness check)

Usage:
  python livecheck.py            # print gate result
  python livecheck.py --strict   # exit code 1 on any failure (for CI / pre-flight)
"""

import asyncio
import argparse
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from config import CFG
import db
import risk
from exchange import build_exchange
import logger


PASS = "✅ PASS"
FAIL = "❌ FAIL"


async def run_checks() -> list[tuple[str, bool, str]]:
    """
    Returns list of (check_name, passed, detail).
    """
    results = []
    await db.init_db()

    # ── 1. Explicit acknowledgement ───────────────────────────────────────────
    ack = CFG.live_acknowledged
    results.append((
        "LIVE_ACKNOWLEDGED",
        ack,
        "Set LIVE_ACKNOWLEDGED=true in .env to confirm intent"
        if not ack else "Acknowledged",
    ))

    # ── 2. API credentials ────────────────────────────────────────────────────
    has_creds = bool(CFG.api_key and CFG.api_secret)
    results.append((
        "API credentials",
        has_creds,
        "API_KEY and API_SECRET must be set" if not has_creds else "Present",
    ))

    # ── 3. Paper trade count ──────────────────────────────────────────────────
    closed = await db.get_closed_count()
    needed = CFG.min_paper_trades_for_live
    trades_ok = closed >= needed
    results.append((
        f"Paper trades ≥ {needed}",
        trades_ok,
        f"Have {closed}, need {needed}"
        if not trades_ok else f"{closed} closed trades on record",
    ))

    # ── 4. Kill-switch not active ─────────────────────────────────────────────
    kill_ok = not risk.kill_switch_active()
    results.append((
        "Kill-switch inactive",
        kill_ok,
        f"Remove {CFG.kill_file} first" if not kill_ok else "Not active",
    ))

    # ── 5. Exchange connectivity ──────────────────────────────────────────────
    # Use paper exchange for connectivity test so no live creds are needed
    # just for the network check.
    ex = build_exchange()
    try:
        ready_ok, ready_reason = await ex.readiness_check()
    except Exception as e:
        ready_ok    = False
        ready_reason = str(e)
    finally:
        await ex.close()

    results.append((
        "Exchange connectivity",
        ready_ok,
        ready_reason,
    ))

    # ── 6. Config validates cleanly ───────────────────────────────────────────
    config_ok   = True
    config_msg  = "OK"
    try:
        # Temporarily force mode=live for validation
        _orig = CFG.mode
        CFG.mode = "live"
        CFG.validate()
        CFG.mode = _orig
    except Exception as e:
        config_ok  = False
        config_msg = str(e)
        CFG.mode   = _orig  # type: ignore

    results.append((
        "Config valid for live",
        config_ok,
        config_msg,
    ))

    return results


def print_results(results: list[tuple[str, bool, str]]) -> bool:
    w = 54
    print()
    print(f"╔{'═'*w}╗")
    print(f"║  🚦 Live-Mode Pre-flight Checklist{'':>{w-35}}║")
    print(f"╠{'─'*w}╣")
    all_pass = True
    for name, passed, detail in results:
        icon = PASS if passed else FAIL
        if not passed:
            all_pass = False
        print(f"║  {icon}  {name:<28}  {detail[:14]:<14}║")
    print(f"╠{'─'*w}╣")
    verdict = "🟢 ALL GATES PASSED — live mode permitted" if all_pass \
        else "🔴 GATES FAILED — live mode BLOCKED"
    print(f"║  {verdict:<{w-2}}║")
    print(f"╚{'═'*w}╝")

    if not all_pass:
        print()
        print("  Failure details:")
        for name, passed, detail in results:
            if not passed:
                print(f"    • {name}: {detail}")
    print()
    return all_pass


async def main(strict: bool = False) -> None:
    print("[livecheck] Running pre-live gate checks...")
    results  = await run_checks()
    all_pass = print_results(results)

    if strict and not all_pass:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-live gate check")
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit with code 1 if any gate fails"
    )
    args = parser.parse_args()
    asyncio.run(main(strict=args.strict))
