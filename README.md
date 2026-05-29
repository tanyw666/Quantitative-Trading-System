# 股票量化系统

这是我们自己的 A 股量化研究、选股、回测和复盘系统。它借鉴参考系统里的优秀思路：配置驱动、A 股交易规则、决策审计、选股追踪和复盘闭环；但不会照搬过重的报告堆叠和硬编码战法，而是先把底层能力做稳。

## 当前定位

第一阶段定位是“研究 + 半自动辅助决策”，不接实盘自动下单。

- 数据层：支持本地 CSV，预留 AkShare 拉取入口。
- 缓存层：优先 Parquet，缺少 PyArrow 时自动降级 CSV。
- 因子层：MA、RSI、ATR、动量、量比、20 日前高等独立因子。
- 策略层：内置趋势突破、强势股筛选，并支持 YAML 条件树策略。
- 回测层：支持 T+1、涨跌停、手续费、印花税、滑点、整手交易、止损。
- 绩效层：收益、年化、波动率、夏普、最大回撤、胜率、盈亏比。
- 审计层：记录每次买入、卖出、风控拦截和失败原因。
- 复盘层：日报、交易日志、选股追踪、未来收益验证。

## 项目结构

```text
src/quant_system/
  data/          数据源、数据路由、缓存读写
  factors/       独立因子库
  strategies/    策略定义、条件树、YAML 策略
  backtest/      回测引擎、撮合、交易记录
  metrics/       绩效指标
  risk/          风控规则
  trace/         决策审计事件
  portfolio/     交易日志、选股追踪
  optimizer/     选股后验验证、策略调优基础
  reports/       Markdown 日报
  storage/       JSONL、表格缓存
  cli.py         命令行入口
configs/         系统和策略配置
data/            样例数据、缓存、复盘记录
tests/           测试
```

## 快速开始

安装依赖：

```powershell
python -m pip install -e .[dev]
```

运行测试：

```powershell
python -m pytest
```

如果 Windows 终端显示中文异常，先切到 UTF-8 代码页，或直接用 Windows Terminal / VS Code 终端查看。

查看命令：

```powershell
python -m quant_system --help
```

运行选股：

```powershell
python -m quant_system screen --csv data/sample_ohlcv.csv --strategy strong_stock_screen --top 10
```

从本地缓存股票池运行选股：

```powershell
python -m quant_system screen --cache-dir data/cache/daily --universe configs/universe_sample.csv --strategy strong_stock_screen
```

候选池会输出综合评分、风险等级和 ATR 参考止损价。当前评分由 20 日动量、量比和低波动分位合成，后续可以继续加入板块强度、涨停梯队、新闻催化等维度。

查看市场温度：

```powershell
python -m quant_system market temperature --csv data/sample_ohlcv.csv --strategy strong_stock_screen
```

生成仓位建议：

```powershell
python -m quant_system portfolio allocate --csv data/sample_ohlcv.csv --strategy strong_stock_screen --cash 100000 --top 5
```

仓位建议会先根据市场温度确定总仓位，再按候选评分分配，并用个股风险等级限制单票上限。它只用于纪律约束，不会自动下单。

交易前纪律检查：

```powershell
python -m quant_system portfolio precheck --csv data/sample_ohlcv.csv --strategy strong_stock_screen --symbol 000001 --entry-price 38 --planned-pct 0.10 --stop-price 35 --target-price 44 --cash 100000 --top 5
```

检查项包括市场状态、策略健康度、是否在候选池、风险等级、买入价偏离、计划仓位、止损距离和盈亏比。

需要可直接打印给盘前使用的清单时，加上 `--format markdown`。

使用系统配置覆盖评分和仓位规则：

```powershell
python -m quant_system screen --csv data/sample_ohlcv.csv --strategy strong_stock_screen --settings configs/system.yaml
```

`configs/system.yaml` 里可以调整候选评分权重、不同市场温度下的总仓位，以及不同风险等级的单票仓位上限。

记录实际交易：

```powershell
python -m quant_system review trade-add --date 2024-01-30 --symbol 000001 --side BUY --price 38 --quantity 100 --reason 突破买入 --strategy strong_stock_screen --market-regime warm --planned-pct 0.12 --actual-pct 0.10 --planned-price 37.5 --stop-price 33.86 --tags 计划内,突破
```

查看交易日志和统计：

```powershell
python -m quant_system review trade-list
python -m quant_system review trade-stats
```

交易日志会记录计划仓位、实际仓位、计划价格、执行偏差、止损价、标签和错误类型，用来做周度复盘和纪律统计。

查看当前持仓：

```powershell
python -m quant_system portfolio positions --journal data/review/trades.jsonl --cash 100000 --price 000001=38
```

持仓视图会从交易日志重建当前数量、平均成本、市值、浮盈亏和总暴露。

检查持仓风险：

```powershell
python -m quant_system portfolio risk --journal data/review/trades.jsonl --cash 100000 --price 000001=38 --stop 000001=33.86 --max-exposure-pct 0.8 --max-position-pct 0.2
```

持仓风险检查会提示总仓位是否超限、单票是否超限、是否触发或接近止损。

检查行情数据健康：

```powershell
python -m quant_system data health --csv data/sample_ohlcv.csv --min-rows 30
```

数据健康检查会提示重复记录、空值、价格异常、历史长度不足和数据滞后问题。

生成周报：

```powershell
python -m quant_system report weekly --csv data/sample_ohlcv.csv --tracker data/review/selections.jsonl --journal data/review/trades.jsonl --output reports/weekly.md
```

周报会汇总市场温度、选股后验收益、交易纪律统计、错误类型和下周改进事项。

生成作战简报：

```powershell
python -m quant_system report briefing --csv data/sample_ohlcv.csv --strategy strong_stock_screen --journal data/review/trades.jsonl --cash 100000 --price 000001=38 --stop 000001=33.86 --output reports/briefing.md
```

作战简报会汇总市场温度、今日候选、仓位计划、当前持仓、持仓风险和今日动作清单，适合作为每天打开系统后的第一屏。

运行参数实验：

```powershell
python -m quant_system optimize experiments --csv data/sample_ohlcv.csv --cases configs/experiments/strong_stock_basic.yaml --horizons 1,3,5 --top 5 --output reports/experiments.json --report-output reports/experiments.md
```

参数实验会按历史日期滚动生成候选，再计算未来收益和胜率，用来比较不同阈值、评分权重和策略风格。

运行回测：

```powershell
python -m quant_system backtest --csv data/sample_ohlcv.csv --strategy strong_stock_screen
```

生成日报，并记录候选股：

```powershell
python -m quant_system report daily --csv data/sample_ohlcv.csv --strategy strong_stock_screen --output reports/daily.md
```

验证历史选股的未来收益：

```powershell
python -m quant_system review selections --tracker data/review/selections.jsonl --csv data/sample_ohlcv.csv --horizons 1,3,5
```

从 AkShare 拉取并缓存 A 股日线：

```powershell
python -m quant_system data fetch-daily --symbol 000001 --start 20240101 --end 20240527 --source akshare
```

真实数据烟测股票池：

```powershell
python -m quant_system data health --cache-dir data/cache/daily --universe configs/universe_smoke.csv --strict
python -m quant_system report briefing --cache-dir data/cache/daily --universe configs/universe_smoke.csv --strategy strong_stock_screen --output reports/real_briefing.md
```

生成真实 A 股股票池：

```powershell
python -m quant_system data universe --output configs/universe_a_share.csv
```

常用过滤：

```powershell
python -m quant_system data universe --output configs/universe_main.csv --exclude-star --exclude-chinext
```

默认会排除 ST 和北交所；可用 `--include-st`、`--include-bj` 放开。

查看板块/行业强度：

```powershell
python -m quant_system market sectors --csv data/sample_sector_ohlcv.csv --strategy strong_stock_screen --top 5
```

如果行情数据包含 `sector`、`industry` 或 `board` 字段，系统会自动识别主线板块，并在作战简报中展示。

按股票池批量刷新缓存：

```powershell
python -m quant_system data fetch-batch --universe configs/universe_sample.csv --start 20240101 --end 20240527 --source akshare
```

使用 YAML 条件树策略：

```powershell
python -m quant_system screen --csv data/sample_ohlcv.csv --config configs/strategies/configurable_strong_stock.yaml
```

## CSV 数据格式

本地 CSV 至少需要包含：

```text
date,open,high,low,close,volume
```

多股票数据建议包含：

```text
symbol,name
```

## 我们吸收的精华

- 配置驱动：筛选条件和策略参数优先写 YAML，避免到处改代码。
- A 股真实规则：回测必须考虑 T+1、涨跌停、整手、费用、印花税和滑点。
- 决策可追溯：不只输出收益，还要知道每次为什么买、为什么卖、为什么被拦截。
- 复盘闭环：选股后自动验证 1/3/5 日表现，让系统自己接受检验。

## 暂不照搬的部分

- 不急着堆 16 个报告模块，先把数据、回测、审计和验证做可信。
- 不把龙头战法、结构战法直接写死进核心引擎，后续作为策略插件接入。
- 不先接实盘下单，避免策略验证不足时把辅助决策误用成自动交易。
