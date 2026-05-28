# Dragon Leader Strategy

This module is the first standalone short-term A-share leader strategy.

## What It Detects

- Limit-up days by board:
  - Main board: 10%
  - STAR / ChiNext: 20%
  - Beijing Stock Exchange: 30%
- Consecutive limit-up count
- Weak-to-strong reversal:
  - Today closes at limit-up
  - Yesterday was not limit-up
  - Yesterday was weak or flat
  - Today did not open with a large gap down
- Volume confirmation through `volume_ratio_20`

## CLI

```powershell
python -m quant_system dragon screen --csv data/sample_dragon_ohlcv.csv --top 5
```

Equivalent generic strategy entry:

```powershell
python -m quant_system screen --csv data/sample_dragon_ohlcv.csv --strategy dragon_leader --top 5
```

The output includes `dragon_score`, `is_limit_up`, `consecutive_limit_up`, `weak_to_strong`, `limit_pct`, regular candidate score, risk grade, and ATR stop reference.

Single-symbol diagnosis:

```powershell
python -m quant_system dragon check --csv data/sample_dragon_ohlcv.csv --symbol 000001
```

The diagnostic snapshot also includes `touch_limit_up`, `failed_limit_up`, `high_acceptance`, `seal_quality_score`, and `recent_failed_limit_up_3`.

The screening output also carries an `entry_gate`:

- `pass`: structure is acceptable for follow-up
- `watch`: structure is usable but needs extra caution
- `block`: avoid chasing or skip the setup

Selections recorded with `--record` keep dragon metadata:

```powershell
python -m quant_system dragon screen --csv data/sample_dragon_ohlcv.csv --record --tracker data/review/selections.jsonl
```

Weekly reports can then summarize forward returns by `entry_gate`, so `pass`, `watch`, and `block` can be judged by actual follow-up performance instead of intuition.

Backtests can filter dragon signals by the same gate:

```powershell
python -m quant_system backtest --csv data/sample_dragon_ohlcv.csv --strategy dragon_leader --entry-gate pass
python -m quant_system backtest --csv data/sample_dragon_ohlcv.csv --strategy dragon_leader --entry-gate pass-watch
python -m quant_system backtest --csv data/sample_dragon_ohlcv.csv --strategy dragon_leader --entry-gate all
```

The backtest engine still enforces A-share limit-up constraints. A signal that appears at limit-up may be blocked from buying, so use `dragon screen --record` plus weekly forward-return validation to judge signal quality alongside executable backtests.

Executable next-open entry model:

```powershell
python -m quant_system backtest --csv data/sample_dragon_next_open_ohlcv.csv --strategy dragon_leader --entry-gate pass --dragon-entry-model next-open --buy-price open --max-next-open-gap 0.07 --min-next-open-gap -0.03
```

Next-open filters:

- `--max-next-open-gap`: skip overheated opens, default `0.07`
- `--min-next-open-gap`: skip weak opens, default `-0.03`
- `--allow-next-open-below-ma5`: disable the default MA5 structure filter

Generate a dual-track validation report:

```powershell
python -m quant_system report dragon --csv data/sample_dragon_ohlcv.csv --entry-gate pass --tracker data/review/selections.jsonl --output reports/dragon_validation.md
python -m quant_system report dragon --csv data/sample_dragon_next_open_ohlcv.csv --entry-gate pass --dragon-entry-model next-open --buy-price open --tracker data/review/selections.jsonl --output reports/dragon_next_open_validation.md
```

This report compares recorded signal forward returns with executable backtest results under the selected `entry_gate`.

Run a parameter grid for executable next-open entries:

```powershell
python -m quant_system optimize experiments --csv data/sample_dragon_next_open_ohlcv.csv --preset dragon_next_open_gap --horizons 1 --top 1 --min-history 25 --output reports/dragon_gap_experiments.json --report-output reports/dragon_gap_experiments.md
```

The built-in `dragon_next_open_gap` preset compares `max_next_open_gap` values of `0.03`, `0.05`, `0.07`, and `0.10` against `min_next_open_gap` values of `-0.01`, `-0.03`, and `-0.05`. For the `next-open` model, reports keep the buy date and executable price context while carrying the previous setup day's dragon metadata (`entry_gate`, `dragon_tags`, seal quality, and state), so parameter evaluation is tied to the original signal quality.

By default the report only recommends a parameter set when the preferred horizon has at least 5 valid samples. For small-sample debugging, the recommendation gate can be loosened explicitly:

```powershell
python -m quant_system optimize experiments --csv data/sample_dragon_next_open_ohlcv.csv --preset dragon_next_open_gap --horizons 1 --top 1 --min-history 25 --recommend-horizon 1 --recommend-min-count 1 --report-output reports/dragon_gap_experiments_relaxed.md
```

To make the recommendation machine-readable for later weekly reports or automation, add `--summary-output`:

```powershell
python -m quant_system optimize experiments --csv data/sample_dragon_next_open_ohlcv.csv --preset dragon_next_open_gap --horizons 1 --top 1 --min-history 25 --recommend-horizon 1 --recommend-min-count 1 --summary-output reports/dragon_gap_experiment_summary.json
```

To turn the recommended parameter set into a reusable strategy YAML:

```powershell
python -m quant_system optimize export-strategy --summary reports/dragon_gap_experiment_summary.json --output configs/strategies/dragon_gap_recommended.yaml
```

The exported YAML can then be fed back into `screen`, `report`, or `backtest` through `--config`.

## Dragon Tags

- `reseal-candidate`: daily bars suggest the stock touched limit-up, traded below the limit price, and still closed at limit-up. This is a conservative daily-bar proxy, not order-book proof.
- `failed-limit-up`: the stock touched the limit price but did not close there.
- `failed-limit-repair`: yesterday failed at limit-up and today closed at limit-up.
- `one-price-limit`: open, low, and close stayed near the limit-up price.
- `high-acceptance`: after a previous limit-up, price closed in the upper part of the daily range without a failed-board signal.

Briefing reports append dragon context for dragon candidates:

```text
dragon 118.0, seal 100.0, state sealed, tags reseal-candidate/high-acceptance
```

## Current Limits

- It does not yet model IPO first-five-trading-day no-limit rules.
- It does not yet use intraday seal strength, failed-board count, or order book data.
- It is a research and decision-support module only, not an auto-trading module.
