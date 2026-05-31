# Strategy Portfolio Manager

策略组合管理器用于把“单一主策略”升级为“主策略 + 辅策略 + 总闸门”的动态选股流程。

## 目标

每日不固定只跑一套策略，而是先判断市场环境，再决定：

- 哪些策略启用；
- 哪些策略暂停；
- 每个策略给多少预算；
- 同一股票被多策略命中时是否加权；
- 单票最多允许多少仓位；
- 最终候选是否进入交易前总闸门。

## 默认配置

默认配置文件：

`configs/strategy_portfolio.yaml`

样本校准后生成的候选配置：

`configs/strategy_portfolio_calibrated.yaml`

当前组合：

| 策略 | 角色 | 使用环境 | 定位 |
| --- | --- | --- | --- |
| `strong_stock_screen` | `main_attack` | hot/warm/neutral | 主攻强趋势、强资金候选 |
| `steady_reversal_sharpe` | `defensive_supplement` | hot/warm/neutral/cold | 低波动、低关注、稳步上涨补充 |
| `trend_breakout` | `probe` | hot/warm | 小预算突破试探 |

## 使用方式

单独筛选：

```powershell
python -m quant_system screen --csv reports\backtests\steady_reversal_input_cache_sample_30.csv --portfolio-config configs\strategy_portfolio.yaml --top 5
```

盘前流程：

```powershell
python -m quant_system workflow premarket --csv <行情CSV> --portfolio-config configs\strategy_portfolio.yaml
```

完整交易日流程：

```powershell
python -m quant_system workflow trading-day --csv <行情CSV> --portfolio-config configs\strategy_portfolio.yaml
```

## 风控行为

组合管理器不会绕过总闸门。它只负责候选组合和策略预算，之后仍然进入：

- 市场温度仓位上限；
- 单票风险等级上限；
- `position_cap_pct` 单票组合上限；
- 交易前检查；
- 下单确认；
- 交易后回写和复盘约束。

同一股票如果被多个策略同时选中，会得到 `strategy_vote_count` 和 `strategy_votes` 标记，但单票仍受 `max_position_pct` 封顶，默认不超过 20%。

## 后续校准重点

后续应继续用样本回测校准：

- 各市场环境下的策略预算；
- `strong_stock_screen` 在 neutral 市场的预算是否仍偏高；
- `steady_reversal_sharpe` 在 cold 市场是否能降低组合回撤；
- 多策略命中加分是否过强；
- `trend_breakout` 是否应该继续保留为试探策略。

## 当前校准结论

基于当前 30 票样本的组合校准结果：

- `probe` 角色在当前样本上拖累表现，校准候选配置先关闭；
- 单票上限从 `20%` 下调到 `18%` 更稳；
- 但当前样本外表现仍偏弱，因此**不建议直接覆盖默认配置**；
- 更合适的做法是：
  - 日常研究继续保留默认配置；
  - 扩大历史样本后，再决定是否把 `strategy_portfolio_calibrated.yaml` 升级为默认版本。
