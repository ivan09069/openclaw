# Trading Skill

## Purpose
Use this skill for strategy controls, bot operations, execution safeguards, and trading-system evaluation.

## Core Objective
Optimize for net PnL, not trade count.

## Core Rules
- Prefer one venue and one pair unless explicitly expanded
- Require expected edge to exceed all-in execution costs
- Do not enable live trading without explicit approval
- Track recent net PnL, drawdown, quote/fill drift, and exposure
- Freeze when controls are breached

## Required Safeguards
Before changing or evaluating a trading system, check:
- mode: paper, sim, testnet, or live
- active pair and venue
- recent realized and unrealized PnL
- fees and slippage assumptions
- position sizing rules
- kill-switch thresholds
- logging and observability status

## Kill Conditions
Freeze or recommend freeze when:
- recent net PnL is negative beyond allowed tolerance
- quote-vs-fill drift is excessive
- daily drawdown breaches limit
- execution mode is unclear
- balances or inventory assumptions are invalid
- observability is too weak to judge system health

## Working Style
1. Confirm current mode
2. Identify pair, venue, and sizing logic
3. Inspect logs and recent outcomes
4. Evaluate edge versus costs
5. Recommend keep, change, or freeze
6. Verify changes with readback or test output

## Change Rules
- Prefer parameter tightening over broad rewrites
- Change one control surface at a time when practical
- Record what changed and why
- Keep rollback simple
- Do not present optimism as evidence

## Reporting Rules
A trading report should state:
- current mode
- pair and venue
- recent PnL state
- principal risks
- recommendation
- exact next action

## Completion Standard
A trading task is complete only when:
- the mode is clear
- the risk state is clear
- the recommendation is evidence-based
- a rollback or freeze path exists
