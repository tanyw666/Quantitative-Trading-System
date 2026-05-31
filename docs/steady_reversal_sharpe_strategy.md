# 类夏普低波反转精选策略

## 定位

这是一条独立的中短线选股策略，核心是：

- 先用类夏普比约束动量，筛出稳步上涨的股票。
- 再用低换手和低振幅做反转精选，避开过热、高关注、高波动的票。
- 默认 20 个交易日调仓一次，持股 5 只。

## 因子落点

因子在 `src/quant_system/factors/technical.py` 中落地：

- `return_10`：10 日总收益
- `return_volatility_10`：10 日涨跌幅标准差
- `like_sharpe_10`：`return_10 / return_volatility_10`
- `turnover_60_avg`：60 日平均换手率
- `amplitude_10_avg`：10 日平均振幅
- `low_turnover_z`：换手率横截面 z-score 取负
- `low_amplitude_z`：振幅横截面 z-score 取负
- `steady_reversal_score`：`low_turnover_z + low_amplitude_z`

## 策略落点

策略类：

- `src/quant_system/strategies/steady_reversal_sharpe.py`

配置：

- `configs/strategies/steady_reversal_sharpe.yaml`

注册名：

- `steady_reversal_sharpe`

## 默认规则

- `like_sharpe_10 > 1.0`
- 按 `steady_reversal_score` 降序选前 5
- `rebalance_period = 20`
- `min_traded_value = 20000000`
- `max_atr_pct = 0.20`
- 价值地雷过滤必须不为 `block`
- 默认必须有 `turnover` / `turnover_rate` 数据，否则不选股，避免策略退化成只看振幅

## 使用命令

```powershell
python -m quant_system screen `
  --csv reports/backtests/structure_calibration_input_cache_sample_30.csv `
  --config configs/strategies/steady_reversal_sharpe.yaml `
  --top 5
```

```powershell
python -m quant_system backtest `
  --csv reports/backtests/structure_calibration_input_cache_sample_30.csv `
  --config configs/strategies/steady_reversal_sharpe.yaml `
  --cash 100000 `
  --buy-price open `
  --execution-timing next_bar
```

## 风控解释

这个策略的风险点不是追高，而是：

- 换手过低导致流动性不足
- 低波动股票突然放量破位
- 20 日调仓周期可能错过快速恶化

所以它已经接入：

- 成交额过滤
- ATR 风险过滤
- 价值地雷过滤
- 回测与策略健康验证
