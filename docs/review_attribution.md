# Review Attribution

`review attribution` is the post-close root-cause report. It combines the review ledger into one answer: what actually broke, which area owns it, and what must be fixed before the next trading session.

## Inputs

- Trade plans: `data/review/trade_plans.jsonl`
- Trade journal: `data/review/trades.jsonl`
- Execution confirmations: `data/review/execution_confirms.jsonl`
- Final order approvals: `data/review/order_approvals.jsonl`
- Approval cooldown constraints: generated from the approval audit
- Gate discipline and trade mistakes: derived from the trade journal
- Lifecycle snapshot: latest record from `data/review/lifecycle_snapshots.jsonl`, or a live snapshot rebuilt from trades when no persisted snapshot exists

## Command

```powershell
python -m quant_system review attribution `
  --trade-log data/review/trades.jsonl `
  --plan-log data/review/trade_plans.jsonl `
  --confirm-log data/review/execution_confirms.jsonl `
  --approval-log data/review/order_approvals.jsonl `
  --lifecycle-log data/review/lifecycle_snapshots.jsonl `
  --format markdown `
  --output reports/review_attribution.md
```

## Output

- `status`: `pass`, `warn`, or `block`
- `score`: starts at 100 and deducts for each warn/block root cause
- `by_area`: root-cause counts across planning, execution, approval, gate, behavior, and lifecycle
- `root_causes`: severity, area, signal, evidence, and next action
- `action_items`: tomorrow's operational fixes in priority order

## How To Use

Run this after the trading-day workflow and after trade fills have been written back. If the report is `block`, the next session should start in no-new-BUY mode until the block-level items are cleared. If it is `warn`, keep size reduced and fix the listed process gaps before adding exposure.

## Workflow Integration

`workflow trading-day` now writes the attribution report and the next-session policy report automatically:

```powershell
python -m quant_system workflow trading-day `
  --csv data/sample_ohlcv.csv `
  --review-attribution-output reports/review_attribution.md `
  --attribution-policy-output reports/attribution_policy.md `
  --summary-output reports/trading_day_workflow.json
```

The workflow summary includes `review_attribution.status`, `score`, `root_cause_count`, and `by_area`. A block-level attribution issue upgrades the workflow status to `block`.

The policy report converts root causes into next-session constraints and discipline advice. To persist those constraints into the review ledger:

```powershell
python -m quant_system workflow trading-day `
  --csv data/sample_ohlcv.csv `
  --record-attribution-policy `
  --constraint-log data/review/strategy_constraints.jsonl `
  --discipline-log data/review/discipline.jsonl `
  --sqlite data/quant.sqlite
```

You can also run it directly:

```powershell
python -m quant_system review attribution-policy `
  --trade-log data/review/trades.jsonl `
  --plan-log data/review/trade_plans.jsonl `
  --confirm-log data/review/execution_confirms.jsonl `
  --approval-log data/review/order_approvals.jsonl `
  --record `
  --format markdown `
  --output reports/attribution_policy.md
```

## SQLite Ledger

Execution confirmations are part of the SQLite review ledger. `portfolio confirm --record --sqlite data/quant.sqlite` persists the confirmation to both JSONL and SQLite.

Historical JSONL logs can be imported with:

```powershell
python -m quant_system data db import-review `
  --db-path data/quant.sqlite `
  --confirm-log data/review/execution_confirms.jsonl
```

After import, `review execution-audit --sqlite data/quant.sqlite` and `review attribution --sqlite data/quant.sqlite` read confirmations from the database.

## Recovery Rules

Attribution constraints now have a staged recovery path:

- `blocked` / `cooldown`: new BUY orders stay paused while block constraints are still inside the policy window.
- `recovery_probe`: after `recover_after_clean_days` clean days and clean review evidence, the strategy may only use reduced probe sizing.
- `recovered`: after the probe window also stays clean, normal sizing is restored.

Recovery evidence is checked before a block is lifted:

- Trade-plan audit must meet `recover_trade_plan_match_rate_min`.
- Unmatched plans and orphan trades must be within the configured maximums.
- Review memory / doctor issues such as missing execution confirmations, stale lifecycle snapshots, or open sell-all tasks must be cleared.

The active policy state is written into strategy health as `policy_state`, `policy_clean_days`, `policy_recovery_ready`, and `policy_recovery_reasons`. Screening output also carries `strategy_actionable` and `strategy_exposure_multiplier`, so a paused strategy can still be inspected without polluting the selection tracker.
