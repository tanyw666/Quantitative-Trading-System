# 每日交易主流程

`workflow daily` 是现在推荐的每日主入口。它把盘前数据检查、候选、仓位、最终作战单、交易驾驶舱、审批冷静期、交易日时间线、交易助手、成交审计、复盘医生、盘后归因和次日约束收敛到一条命令里。

最重要的输出是 `reports/today_trade_brief.md`，也就是“今日交易主清单”：先看它，再决定今天是否允许开新仓。

## 推荐命令

```powershell
python -m quant_system workflow daily `
  --csv data/sample_ohlcv.csv `
  --strategy strong_stock_screen `
  --record-state `
  --record-trade-plans `
  --summary-output reports/trading_day_workflow.json
```

如果需要指定输出位置：

```powershell
python -m quant_system workflow daily `
  --csv data/sample_ohlcv.csv `
  --daily-output reports/today_trade_brief.md `
  --battle-plan-output reports/final_battle_plan.md `
  --assistant-output reports/trading_assistant.md `
  --review-attribution-output reports/review_attribution.md `
  --summary-output reports/trading_day_workflow.json
```

## 推荐顺序

1. `workflow daily`
2. 查看 `reports/today_trade_brief.md`
3. 对允许买入的标的运行 `portfolio confirm`
4. 下单前运行 `portfolio tradable` 或 `portfolio approve`
5. 成交后立刻运行 `review trade-add`
6. 盘后运行 `review execution-audit`
7. 盘后运行 `review attribution`
8. 次日开盘前查看约束和纪律建议

## 完整工作流

```powershell
python -m quant_system workflow trading-day `
  --csv data/sample_ohlcv.csv `
  --strategy strong_stock_screen `
  --premarket-output reports/premarket.md `
  --battle-plan-output reports/final_battle_plan.md `
  --cockpit-output reports/trading_cockpit.md `
  --execution-audit-output reports/execution_audit.md `
  --lifecycle-output reports/lifecycle.md `
  --timeline-output reports/trading_timeline.md `
  --assistant-output reports/trading_assistant.md `
  --daily-output reports/today_trade_brief.md `
  --trade-plan-batch-output reports/trade_plan_batch.md `
  --review-doctor-output reports/review_doctor.md `
  --review-attribution-output reports/review_attribution.md `
  --attribution-policy-output reports/attribution_policy.md `
  --summary-output reports/trading_day_workflow.json
```

## 持久化交易计划

交易计划默认只生成报告，不写入日志。需要留档时加 `--record-trade-plans`：

```powershell
python -m quant_system workflow trading-day `
  --csv data/sample_ohlcv.csv `
  --strategy strong_stock_screen `
  --record-trade-plans `
  --trade-plan-log data/review/trade_plans.jsonl
```

重复运行会用内容指纹跳过重复计划，避免日志膨胀。

## 今日交易主清单

`today_trade_brief.md` 会固定回答：

- 今天能不能开新仓
- 哪些票允许买
- 每只最多买多少
- 哪些票禁止或只能观察
- 哪些持仓或纪律问题必须先处理
- 盘后需要补哪些复盘动作
- 下一步应该跑哪些命令

## 下单前安全检查

下单前建议至少保留这条链路：

```powershell
python -m quant_system portfolio approve `
  --csv data/sample_ohlcv.csv `
  --strategy strong_stock_screen `
  --symbol 000001 `
  --current-price 10.20 `
  --planned-pct 0.05 `
  --stop-price 9.70 `
  --target-price 12.00 `
  --record
```

`portfolio tradable` 和 `portfolio approve` 会更保守地处理：

- 停牌或零成交量
- 缺失、NaN 或异常 OHLCV
- 陈旧 K 线
- 主板、ST、创业板、科创板、北交所不同涨跌停幅度
- 涨停附近追买和跌停附近流动性风险

如果检查结果是 `block`，不要下单；如果是 `warn`，只能在手工接受预警并降低风险后继续。

## 成交后回写

成交后用 `review trade-add` 写入交易日志。系统会自动把以下买入标记为纪律例外：

- gate 是 `warn` 或 `block`
- execution confirmation 是 `block`
- 实际买入数量超过 confirmation 建议数量
- 实际成交价明显高于 confirmation 价格
- final order approval 是 `block`
- 实际买入数量超过 final order approval 建议数量

如果确实是计划内破例，必须写清楚 `--exception-reason`：

```powershell
python -m quant_system review trade-add `
  --date 2026-05-30 `
  --symbol 000001 `
  --side BUY `
  --price 10.20 `
  --quantity 500 `
  --reason "按审批单执行" `
  --order-approval reports/order_approval.json `
  --exception-reason "指数急跌后按预案缩量试错"
```

没有说明理由的纪律例外会被 `review exceptions` 列入缺少理由清单。

## 复盘医生

`review doctor` 检查交易闭环是否完整，适合盘后或次日盘前运行：

```powershell
python -m quant_system review doctor `
  --tracker data/review/selections.jsonl `
  --journal data/review/trades.jsonl `
  --trade-plan-log data/review/trade_plans.jsonl `
  --confirm-log data/review/execution_confirms.jsonl `
  --state-log data/review/trading_day_states.jsonl `
  --format markdown
```

## 默认配置

默认交易日阶段提示词在 `configs/system.yaml` 的 `trading_day.phases` 中。
