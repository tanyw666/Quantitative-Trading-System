# 每本书的借鉴落点

这份清单按你提供的书名逐本对应到系统里的真实落点。这里的“借鉴”不是摘抄观点，而是转成系统自己的规则、因子、闸门、仓位、退出或复盘纪律。

## 1. 《日本蜡烛图技术》

落点：

- K 线质量字段：`close_position_in_range`、`upper_shadow_pct`、`lower_shadow_pct`、`body_pct`
- 蜡烛图警报：`candle_warning_count`
- 衰竭与上影线风险识别
- 入场结构评分：`entry_structure_score`
- 止盈/减仓参考：长上影、放量滞涨、收盘位置变差

主要模块：

- `src/quant_system/factors/technical.py`
- `src/quant_system/risk/pretrade.py`

## 2. 《股票大作手回忆录》

落点：

- 顺势而为，不在弱结构里强行找便宜
- 主升趋势优先：`trend_quality_score`
- 试仓、加仓、只加盈利仓
- 结构破坏后不和市场争辩

主要模块：

- `src/quant_system/factors/technical.py`
- `src/quant_system/risk/sizing.py`
- `src/quant_system/portfolio/lifecycle_rules.py`

## 3. 《证券分析》

落点：

- 价值地雷过滤
- ST、退市风险、负 PE/PB、缺失市值信息预警
- 对短线系统增加“先排雷，再谈进攻”的底线

主要模块：

- `src/quant_system/screening/value_filters.py`
- `src/quant_system/risk/pretrade.py`

## 4. 《聪明的投资者》

落点：

- 安全边际思想转成禁买和预警项
- 不碰明显有财务/治理/估值异常的票
- 把“便宜”与“可交易”分开，不因低估值自动买入

主要模块：

- `src/quant_system/screening/value_filters.py`
- `src/quant_system/screening/scoring.py`

## 5. 《巴菲特致股东信》

落点：

- 避免长期质量差、治理差、资本配置差的公司
- 市场环境不好时，现金也是仓位
- 仓位进攻/防守跟随市场温度，而不是情绪冲动

主要模块：

- `src/quant_system/screening/value_filters.py`
- `src/quant_system/risk/sizing.py`

## 6. 《量价分析》

落点：

- 放量确认、缩量回踩、量价背离
- `volume_ratio_20`
- `volume_confirmation_score`
- `volume_price_state`
- 放量长上影不等于强势，必须结合收盘位置判断

主要模块：

- `src/quant_system/factors/technical.py`
- `src/quant_system/risk/pretrade.py`

## 7. 《解读盘口》

落点：

- 用日线 OHLCV 近似盘口压力
- `tape_pressure_score`
- `tape_distribution_warning`
- `tape_accumulation_hint`
- 放量冲高回落、弱收盘、上影线形成派发风险

主要模块：

- `src/quant_system/factors/technical.py`
- `src/quant_system/risk/pretrade.py`

## 8. 《专业投机原理》

落点：

- 先试仓，证明正确后再加仓
- 不向亏损仓加码
- 单笔风险、止损距离、仓位上限约束
- 趋势不对时先退，不幻想

主要模块：

- `src/quant_system/risk/sizing.py`
- `src/quant_system/portfolio/lifecycle_rules.py`
- `src/quant_system/portfolio/exit_plan.py`

## 9. 《交易心理分析》

落点：

- 破例交易必须记录理由
- 未按计划交易进入纪律异常
- 连续犯错触发冷静期、降仓或禁开新仓
- 把贪、急、怕、报复交易转成可记录标签

主要模块：

- `src/quant_system/portfolio/discipline.py`
- `src/quant_system/risk/approval_cooldown.py`
- `src/quant_system/risk/constraint_policy.py`
- `src/quant_system/reports/discipline_exceptions.py`

## 10. 《道德经》

落点：

- 市场不支持进攻时，以守为攻
- 冷市场降低仓位，冰冻市场不开新仓
- 不强为，不在不适合交易的环境里硬交易

主要模块：

- `src/quant_system/risk/sizing.py`
- `src/quant_system/market/temperature.py`
- `src/quant_system/reports/final_battle_plan.py`

## 11. 《孙子兵法》

落点：

- 先看战场，再决定进攻
- 市场温度决定仓位上限
- 候选、仓位、作战计划、下单审批形成战术闭环
- 不打无准备之仗，下单前必须过闸门

主要模块：

- `src/quant_system/risk/pretrade.py`
- `src/quant_system/risk/sizing.py`
- `src/quant_system/reports/final_battle_plan.py`
- `src/quant_system/reports/trading_cockpit.py`

## 12. 《四书五经》

落点：

- 纪律、复盘、修身式交易流程
- 错误不只是记录，还要转成次日约束
- 交易行为要可追责、可修正、可恢复

主要模块：

- `src/quant_system/portfolio/discipline.py`
- `src/quant_system/portfolio/discipline_adherence.py`
- `src/quant_system/reports/review_doctor.py`

## 13. 《三十六计》

落点：

- 不追高，等位置
- 允许观察，不强行出手
- 对“看似机会”的诱多结构做假突破过滤
- 把战术等待转成 `warn`、`watch`、`block`

主要模块：

- `src/quant_system/factors/technical.py`
- `src/quant_system/risk/pretrade.py`
- `src/quant_system/reports/trading_assistant.py`

## 14. 《羊皮卷》

落点：

- 重复执行正确流程
- 每笔交易后记录行为与情绪
- 用固定复盘动作代替临场随意性

主要模块：

- `src/quant_system/portfolio/journal.py`
- `src/quant_system/reports/discipline_summary.py`
- `src/quant_system/reports/review_history.py`

## 15. 《人性的弱点》

落点：

- 防止自我合理化
- 破例必须写明原因，不能事后美化
- 复盘时把行为偏差拆成可改进项

主要模块：

- `src/quant_system/portfolio/discipline.py`
- `src/quant_system/reports/discipline_exceptions.py`
- `src/quant_system/reports/review_doctor.py`

## 16. 《诸子百家》

落点：

- 不把一种市场观强套所有行情
- 用多视角规则分层：选股、入场、仓位、退出、纪律
- 系统允许“观察、等待、禁买、降仓、恢复”多种状态

主要模块：

- `configs/rules/book_rule_mapping.yaml`
- `src/quant_system/risk/constraint_policy.py`
- `src/quant_system/reports/trading_assistant.py`

## 17. 《三国》

落点：

- 战役思维，而不是单笔赌博
- 主线、节奏、攻守切换
- 先处理持仓风险，再考虑新机会
- 每日交易主流程统一候选、仓位、作战计划、审批和复盘

主要模块：

- `src/quant_system/reports/final_battle_plan.py`
- `src/quant_system/reports/trading_cockpit.py`
- `src/quant_system/reports/daily_trade_brief.py`
- `src/quant_system/portfolio/trading_day_state.py`

## 总结

这些书最终被落成五层：

- 选股层：趋势质量、量价确认、盘口压力、价值地雷过滤
- 入场层：结构评分、假突破过滤、追高风险、下单前确认
- 仓位层：市场温度、单票风险、试仓加仓、连续犯错降仓
- 退出层：止损、止盈、结构失效、持仓生命周期
- 纪律层：破例记录、冷静期、复盘问责、次日约束

对应的机器可读总映射在 `configs/rules/book_rule_mapping.yaml`。
