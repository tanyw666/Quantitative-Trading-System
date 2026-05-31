# 回测可信度说明

本系统的回测默认采用更保守的成交时序：

1. 当天 K 线收盘后产生信号。
2. 下一根同股票 K 线才尝试成交。
3. 默认使用下一根 K 线的 `open` 作为成交基准价。
4. 若下一根 K 线停牌、成交量为 0、价格缺失、涨停买入或跌停卖出，则订单不成交，并写入决策审计事件。

这样做的目的，是避免把“看到当天收盘价之后又假装当天成交”的未来函数收益算进策略表现。

## 参数

- `execution_timing=next_bar`：默认模式，信号日和成交日分离。
- `execution_timing=same_bar`：兼容旧回测或特殊研究用途，不建议作为实盘决策依据。
- `buy_price_field=open`：默认使用下一根 bar 的开盘价成交。
- `buy_price_field=close`：仍然支持，但只建议用于特定收盘执行假设。
- `sell_price_field`：不配置时跟随 `buy_price_field`。

## CLI 示例

```powershell
python -m quant_system backtest `
  --csv data/sample_ohlcv.csv `
  --strategy trend_breakout `
  --cash 100000 `
  --execution-timing next_bar `
  --buy-price open
```

二期可信度审计可以一次性检查多策略、样本内/样本外、市场环境分组和成交阻塞原因：

```powershell
python -m quant_system optimize backtest-reliability `
  --csv data/sample_ohlcv.csv `
  --strategy trend_breakout `
  --strategy strong_stock_screen `
  --format markdown `
  --output reports/backtests/reliability.md
```

审计入口会先运行 OHLCV 健康检查。若数据状态为 `fail`，系统会阻断回测排名，避免用坏数据生成交易结论。常用控制项：

- `--min-rows-per-symbol 30`
- `--max-stale-days 10`
- `--as-of 2026-05-31`

如果要审计 YAML 策略配置，可以使用：

```powershell
python -m quant_system optimize backtest-reliability `
  --csv data/sample_ohlcv.csv `
  --config configs/strategies/trend_breakout.yaml `
  --format json
```

## 审计记录

回测会把以下无法成交原因记录到 `DecisionRecorder`：

- `Signal queued for next bar execution`
- `Limit-up blocks buy`
- `Limit-down blocks sell`
- `Suspended or invalid bar blocks buy`
- `Suspended or invalid bar blocks sell`
- `No next bar to execute signal`
- `T+1 blocks same-day sell`

这些记录用于后续检查策略收益是否来自真实可成交机会，而不是来自数据或时序假设。
