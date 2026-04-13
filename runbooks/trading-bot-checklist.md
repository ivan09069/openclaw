# Trading Bot Checklist

## Goal
Check system state before changing strategy or execution settings.

## Checklist
- confirm mode: sim, paper, testnet, or live
- confirm pair and venue
- inspect recent PnL
- inspect fees and slippage assumptions
- inspect drawdown and kill-switch thresholds
- inspect observability/logging health
- prefer freeze over blind optimism

## Commands
pwd
ls -l
find . -maxdepth 2 -type f | sort | sed -n '1,120p'
grep -RniE 'DRY_RUN|PAPER|LIVE|SANDBOX|PAIR|PRODUCT|SYMBOL|MAX_DRAWDOWN|KILL|SLIPPAGE|FEE' . 2>/dev/null | sed -n '1,200p'

## Verify
- execution mode is clear
- risk controls are visible
- current target pair/venue is known
