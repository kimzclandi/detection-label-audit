# 检测标签复核排序与错误定位诊断

[![CI](https://github.com/kimzclandi/detection-label-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/kimzclandi/detection-label-audit/actions/workflows/ci.yml)

给定已有检测框和参考标签，在固定复核图数下，哪些疑似错误应先检查？本项目实现几何检查、模型一致性候选、候选抑制 guard 与排序回放，并区分**选中污染图片**和**定位注入目标**。

复用上游 BDD100K 检测预测，**没有新增模型训练或推理**。当前方法比较来自开发集人工合成污染；真实标签错误上的效果仍未验证。

## 当前结果

36 张开发图、35 个来源组，三次既有污染运行，每次 8 图预算，合计 **24 次选图**，不是 24 张独立图片。

| 指标 | 原组合 | guard |
|---|---:|---:|
| 选中含注入错误的图片 | 11/24（45.83%） | 17/24（70.83%） |
| 选中且有证据严格定位注入目标 | 6/24 | 12/24 |
| 选中且定位证据达到图内最高分 | 3/24 | 7/24 |
| 全排序范围内可严格定位的注入次数 | 16/54 | 16/54 |

两方法全范围可定位的 **16 个 (seed, image) 集合相同**。guard 的当前收益主要是排序清理：更多已有有效线索进入前 8 图。**70.83% 是开发集合成污染的图级命中率，不是定位准确率或真实标签效果。** 严格定位是事后定义的操作标准，也不能替代独立人工裁决。

[定位定义、反例与结果](docs/LOCALIZATION_V4.md) · [开发集机制诊断](docs/DIAGNOSIS_V2.md) · [逐条定位记录](reports/localization_v4/result.json)

原随机对照存在同 seed 耦合，已另行冻结独立随机流纠正，原失败保留。纠正后随机与几何方法的开发集平均 P@8 均为 50%；这仍是探索性比较。早期 120 图实验的 100% 命中主要来自重复/坐标错误，与当前数据和预算不同，见[历史索引](docs/RESEARCH_INDEX.md)。

## 查看与运行

```bash
uv sync --locked --python 3.12
uv run python scripts/localization_v4.py verify
uv run python scripts/diagnose_v2.py verify
uv run python scripts/correct_control_v2.py verify
uv run python scripts/readiness_v3.py verify
uv run streamlit run dashboard.py --server.address 127.0.0.1
```

默认打开 **「定位归因 v4：事后诊断」**查看上表和逐例归因；「开发诊断 v2：探索性」展示纠正后的随机对照。「可控合成污染」属于早期 120 图实验。命令重算已公开记录并核对冻结身份，不下载模型、不开展新实验；保留池 `verify` 只核验清单，不评分。

[完整复现与来源](docs/REPRODUCE.md) · [数据许可](DATA_LICENSE.md) · [CI 检查范围](.github/workflows/ci.yml)

## 真实标签评测状态

- 旧 40 图仅有两人报告的探索性批量反馈：未发现明确错误。A 直接报告，B 经 A 转述；缺少逐图提交、理由和正式裁决，不能当作“确认无错误”的金标准。[反馈来源及限制](docs/HUMAN_FEEDBACK_V1.md)说明原始记录的证据等级。
- 59 图保留池已核验来源隔离与输入身份，**尚未评分**，没有新的独立真实裁决。详见[资格及门禁](docs/READINESS_V3.md)。
- 自动问题线索仍需复核；未证明真实错误检出率、自动修复效果或训练收益。

## 实现与贡献范围

仓库实现[审计候选](src/label_audit.py)、[开发诊断](scripts/diagnose_v2.py)、[定位归因](scripts/localization_v4.py)和人工提交校验。上游模型预测与参考标签来自 [driving-data-engine](https://github.com/kimzclandi/driving-data-engine)，不计为本项目新增模型实验。代码、测试和文档使用 AI 辅助开发；AI 视觉意见未作为人工裁决。

原始预测、污染记录、冻结协议、无效随机对照、统计修复和人工反馈均保留。[历史与方法文档](docs/RESEARCH_INDEX.md)集中列出各阶段资料。代码 [MIT](LICENSE)，派生数据遵循上游许可。
