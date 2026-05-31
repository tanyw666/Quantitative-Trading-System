# Strategy Portfolio Calibration Result

校准命令：

```powershell
python -m quant_system optimize portfolio-calibration --csv reports\backtests\steady_reversal_input_cache_sample_30.csv --portfolio-config configs\strategy_portfolio.yaml --preset compact --rebalance-period 20 --max-positions 5 --min-history-days 40 --cash 100000 --buy-price open --execution-timing next_bar --format markdown --output reports\backtests\strategy_portfolio_calibration.md
```

输出报告：

`reports/backtests/strategy_portfolio_calibration.md`

## 本次结论

- 本次校准比较了 6 组组合参数。
- 当前样本下最优变体是 `no_probe`。
- 相比 baseline，`no_probe` 的目标分数略好。
- 但最优变体的样本外收益仍为负，因此不能视为已稳定可推广。

## 结构性发现

1. `probe` 策略在当前样本中没有提供有效增益。  
   更具体地说，保留 `trend_breakout` 的组合没有比关闭它的组合更优。

2. 单票上限偏大的版本更容易带来样本外回撤。  
   `20%` 上限在这次样本里并不优于 `18%` 或 `16%`。

3. 多策略重复命中加分目前没有证明有明显正贡献。  
   `duplicate_vote_bonus` 需要继续在更大样本上验证。

## 当前建议

- 默认配置继续保留：`configs/strategy_portfolio.yaml`
- 候选校准版配置：`configs/strategy_portfolio_calibrated.yaml`
- 在更大历史样本、更多市场阶段上继续验证后，再决定是否切默认。
