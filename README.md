# 股票量化系统

一个面向 A 股研究、选股、仓位管理、交易前风控、盘中确认、成交复盘和次日约束的本地量化工具箱。

## 当前定位

- 研究回测
- 半自动辅助决策
- 交易前总闸门
- 盘中确认与最终审批
- 交易后复盘归因
- 次日策略约束

## 每日主流程

推荐每天先跑这一条命令：

```powershell
python -m quant_system workflow daily `
  --csv data/sample_ohlcv.csv `
  --strategy strong_stock_screen `
  --record-state `
  --record-trade-plans `
  --summary-output reports/trading_day_workflow.json
```

最重要的输出：

- `reports/today_trade_brief.md`：今日交易主清单
- `reports/final_battle_plan.md`：最终作战单
- `reports/trading_assistant.md`：交易助手
- `reports/trading_cockpit.md`：交易驾驶舱
- `reports/review_attribution.md`：盘后复盘归因
- `reports/trading_day_workflow.json`：机器可读工作流摘要

## 今日交易主清单

`today_trade_brief.md` 会固定回答：

- 今天能不能开新仓
- 哪些票允许买
- 每只最多买多少
- 哪些票禁止或只能观察
- 哪些持仓必须先处理
- 哪些复盘缺口必须补
- 下一步应该跑哪些命令

## 交易安全规则

- `portfolio tradable` 会保守处理停牌、零成交量、缺失/异常 OHLCV、价格 NaN、陈旧 K 线和涨跌停附近交易。
- 涨跌停会按 A 股板块自动推断：主板 10%，ST 5%，创业板/科创板 20%，北交所 30%。
- `review trade-add` 记录买入时，如果发现你越过了 gate、execution confirmation 或 final order approval，会自动标记为纪律例外。
- 纪律例外如果没有 `--exception-reason`，会被标记为 `exception-missing-reason`，复盘报告会列入“缺少理由”清单。

## 常用命令

```powershell
python -m quant_system screen --csv data/sample_ohlcv.csv --strategy strong_stock_screen --top 10
python -m quant_system portfolio allocate --csv data/sample_ohlcv.csv --strategy strong_stock_screen --cash 100000 --top 5
python -m quant_system portfolio precheck --csv data/sample_ohlcv.csv --strategy strong_stock_screen --symbol 000001 --entry-price 38 --planned-pct 0.10 --stop-price 35 --target-price 44
python -m quant_system portfolio approve --csv data/sample_ohlcv.csv --strategy strong_stock_screen --symbol 000001 --current-price 38 --planned-pct 0.10 --stop-price 35 --target-price 44 --record
python -m quant_system review exceptions --format markdown --output reports/discipline_exceptions.md
python -m quant_system review attribution --format markdown --output reports/review_attribution.md
```

## 配置

- 默认系统配置：`configs/system.yaml`
- 交易日阶段模板：`trading_day.phases`
- 风险约束：`risk.constraint_policy`

## 测试

```powershell
python -m pytest
```
