# 选股和风控加固说明

本轮加固目标是让系统在真实数据验证前先减少噪音候选，并把选股字段和交易前检查统一起来。

## 新增候选质量字段

因子层现在会输出：

- `ma20_slope_5`：MA20 五日斜率，用于确认中期趋势是否走强。
- `close_to_ma20`：收盘价相对 MA20 的乖离，避免追太远。
- `close_to_rolling_high_20`：价格相对过去 20 日高点的位置。
- `traded_value`：`close * volume` 的成交额代理，用于流动性过滤。
- `rsi_14`：短线热度检查。

## 策略过滤

`strong_stock_screen` 和 `trend_breakout` 已支持以下参数：

- `min_ma20_slope`
- `max_close_ma20_gap`
- `max_volume_ratio`
- `max_rsi`
- `min_traded_value`
- `max_atr_pct`

默认 YAML 策略已启用更严格的流动性和趋势质量约束。若真实数据里 `volume` 单位与成交额代理不匹配，需要根据数据源单位调整 `min_traded_value`。

## 交易前风控

`portfolio precheck` 会基于候选快照补充三类检查：

- `candidate_liquidity`：成交额代理太低时阻断新开仓。
- `candidate_trend_quality`：MA20 斜率为负时阻断，乖离过大时预警。
- `candidate_heat`：RSI 或量比过热时预警，避免一致性高潮追高。

这些规则不会替代人工判断，但会让系统在下单前明确指出“为什么不该买”。
