# 策略参数实验报告

生成日期：2026-05-27

## 1. 推荐结论

- 推荐参数组：conservative
- 参考周期：3日
- 平均收益：8.82%
- 胜率：100.0%
- 样本数：1
- 推荐原因：按3日平均收益优先、胜率其次、样本数再次排序。

## 2. 实验明细

| 参数组 | 周期 | 样本数 | 平均收益 | 胜率 | 参数 |
| --- | ---: | ---: | ---: | ---: | --- |
| conservative | 1日 | 1 | 2.94% | 100.0% | min_20d_return=0.18, min_volume_ratio=1.8, max_atr_pct=0.08 |
| conservative | 3日 | 1 | 8.82% | 100.0% | min_20d_return=0.18, min_volume_ratio=1.8, max_atr_pct=0.08 |
| conservative | 5日 | 1 | 11.76% | 100.0% | min_20d_return=0.18, min_volume_ratio=1.8, max_atr_pct=0.08 |
| balanced | 1日 | 3 | 2.86% | 100.0% | min_20d_return=0.12, min_volume_ratio=1.5, max_atr_pct=0.12 |
| balanced | 3日 | 3 | 5.75% | 100.0% | min_20d_return=0.12, min_volume_ratio=1.5, max_atr_pct=0.12 |
| balanced | 5日 | 1 | 11.76% | 100.0% | min_20d_return=0.12, min_volume_ratio=1.5, max_atr_pct=0.12 |
| aggressive | 1日 | 5 | 2.29% | 80.0% | min_20d_return=0.08, min_volume_ratio=1.2, max_atr_pct=0.16 |
| aggressive | 3日 | 3 | 5.75% | 100.0% | min_20d_return=0.08, min_volume_ratio=1.2, max_atr_pct=0.16 |
| aggressive | 5日 | 1 | 11.76% | 100.0% | min_20d_return=0.08, min_volume_ratio=1.2, max_atr_pct=0.16 |

## 3. 使用提醒

- 优先选择样本数足够、收益和胜率都稳定的参数组，不要只看最高收益。
- 参数实验是研究工具，不代表未来收益保证。
