# Book Rule Mapping

This document is the human-readable companion to
`configs/rules/book_rule_mapping.yaml`.

The rulebook is organized by system position, not by book title. Each book is
used only where its ideas can improve a real trading decision.

## Coverage Check

`user_book_coverage` in the YAML maps every book provided by the user to one or
more concrete rule ids. The coverage is intentionally explicit so future changes
can check whether a book is only mentioned in prose or actually connected to a
selection, entry, sizing, exit, or discipline rule.

## Execution Order

1. Selection layer: decide which stocks deserve attention.
2. Entry layer: decide when a candidate can become an order.
3. Sizing layer: decide how much risk is allowed.
4. Exit layer: decide when risk must be reduced or closed.
5. Discipline layer: convert process errors into future constraints.

## Book Groups

### Pattern And Tape Reading

Books:

- Japanese Candlestick Charting Techniques
- Volume Price Analysis
- Tape Reading and Market Tactics

System use:

- Candle warning fields
- Volume-price confirmation
- False breakout detection
- Entry structure scoring
- Distribution and exhaustion warnings

### Trend And Speculation Execution

Books:

- Reminiscences of a Stock Operator
- Methods of a Wall Street Master
- The Art of War
- The Thirty-Six Stratagems
- Romance of the Three Kingdoms

System use:

- Trend-following bias
- Probe then pyramid
- Reduce when the battle field turns against the trade
- Offense/defense switching by market regime
- Campaign thinking instead of isolated impulse trades

### Value And Landmine Filtering

Books:

- Security Analysis
- The Intelligent Investor
- Berkshire Hathaway Letters to Shareholders

System use:

- ST, delisting, and balance-sheet risk filters
- Valuation and quality warnings
- Capital allocation and governance red flags
- Avoiding short-term trades in structurally fragile companies

### Discipline And Psychology

Books:

- Trading in the Zone
- Tao Te Ching
- The Four Books and Five Classics
- The Greatest Salesman in the World
- How to Win Friends and Influence People
- Hundred Schools of Thought

System use:

- Exception logging
- Cooldowns
- Repeated-error constraints
- Emotion tags
- Next-day risk limits
- Recovery requirements after violations

## Rule Shape

Every rule in the YAML file must include:

- `id`: stable rule identifier.
- `layer`: one of `selection`, `entry`, `sizing`, `exit`, `discipline`.
- `source_books`: book group that inspired the rule.
- `principle`: system-owned summary of the idea.
- `quant_rules`: rules the system can check with data.
- `manual_checks`: questions that still need human confirmation.
- `cognitive_reminders`: useful ideas that should not become hard rules.
- `system_targets`: modules where the rule should eventually land.
- `rollout_priority`: rollout order.

## Current Rollout Plan

P0 rules should be implemented first:

- `selection.trend_quality`
- `selection.volume_price_confirmation`
- `entry.confirmation_not_prediction`
- `entry.no_chase_zone`
- `sizing.probe_then_pyramid`
- `sizing.market_offense_defense`
- `exit.stop_means_exit`
- `discipline.exception_has_cost`
- `discipline.review_to_constraint`

P1 rules are useful but should follow after the core trading loop is stable:

- `selection.value_landmine_filter`
- `exit.profit_without_regret`

## Why This Order

The goal is not to make the system quote books. The goal is to make the system
behave better:

- Better candidates before better orders.
- Better entries before bigger size.
- Better risk limits before more automation.
- Better review constraints before strategy expansion.
