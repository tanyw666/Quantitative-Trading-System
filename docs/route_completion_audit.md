# Route Completion Audit

This file audits the completion status of the book-rule rollout route and the
follow-up calibration work.

## Status Summary

### 1. Value filter, sizing, exit, tape-reading proxy, and discipline workflow

Status: completed

Landings:

- Value landmine filter:
  - `src/quant_system/screening/value_filters.py`
  - `src/quant_system/risk/pretrade.py`
- Position sizing and offense/defense exposure:
  - `src/quant_system/risk/sizing.py`
- Exit planning and stop discipline:
  - `src/quant_system/portfolio/exit_plan.py`
- Tape-reading proxy and false-breakout filtering:
  - `src/quant_system/factors/technical.py`
  - `src/quant_system/risk/pretrade.py`
- Discipline, exception cost, cooldown, and next-day constraints:
  - `src/quant_system/portfolio/discipline.py`
  - `src/quant_system/risk/constraint_policy.py`
  - `src/quant_system/risk/approval_cooldown.py`
  - `src/quant_system/portfolio/lifecycle_rules.py`

### 2. Daily trading main workflow

Status: completed

Landings:

- `workflow daily`
- `workflow trading-day`
- `docs/trading_day_workflow.md`
- `src/quant_system/reports/final_battle_plan.py`
- `src/quant_system/reports/trading_cockpit.py`
- `src/quant_system/reports/trading_assistant.py`
- `src/quant_system/reports/daily_trade_brief.py`

### 3. Full regression confirmation

Status: completed

Latest regression result:

- `492 passed`

Regression coverage includes:

- factors
- screening
- pretrade gates
- configurable strategies
- workflow commands
- backtest reliability
- structure calibration CLI

### 4. Strategy parameter calibration and sample backtest validation

Status: completed

Artifacts:

- `reports/backtests/structure_parameter_calibration_focus.md`
- `reports/backtests/structure_parameter_calibration_focus.json`
- `reports/backtests/book_rules_backtest_reliability.md`

Current best structure calibration result on the sampled cache dataset:

- `min_entry_structure_score = 55`
- `max_chase_risk_score = 35`
- `block_false_breakout = true`
- total return about `31.40%`
- max drawdown about `-19.62%`

### 5. Book coverage, route completion, and backtest conclusion summary

Status: completed

Artifacts:

- explicit coverage map:
  - `configs/rules/book_rule_mapping.yaml`
- readable mapping notes:
  - `docs/book_rule_mapping.md`
- this audit file:
  - `docs/route_completion_audit.md`

## Remaining Gaps

The route is complete, but optimization is not finished forever.

Open improvement areas:

- drawdown is still too large for live confidence
- `trend_breakout` remains weak on the sampled history
- out-of-sample performance is still softer than in-sample performance
- calibration currently uses a sampled cache dataset rather than a broader market-wide history

These are not rollout-completion gaps. They are strategy-quality gaps for the
next round of refinement.
