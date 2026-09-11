# 复现、来源和证据身份

`uv sync --locked --python 3.12` 创建独立环境；`scripts/run.py verify` 从固定参考框/预测重建三个污染版本、重新排序、复算18组指标，逐项比较保存结果；`metric_audit.py`重算后续的预算保持统计修复。所有源代码和参考摘要在协议及Git冻结提交 `ffef670` 可查。`reference.json`记录每个上游预测文件和原始标签文件摘要、图像摘要及固定模型SHA。

报告中的真实参考框和检测输出复用 `kimzclandi/driving-data-engine@3a0843db83812e1775bd4144aa0c2087cb34d851`；不声称本项目新增神经推理或训练。框映射沿用七类COCO子集，rider并入person，故类冲突可能来自映射而非真实标签错误。原始BDD标签未独立裁决，只有注入变化可作为确定评测真值。小型派生标签/预测公开分发并保留BDD许可，图像和权重不分发。

审计输入仅含id/group/width/height/labels/predictions。真值字典只交给评测器；测试验证额外truth字段拒绝、原始标签不被注入器修改、五类污染数量、固定预算分母、不可覆盖、异常坐标、模型候选待复核。此隔离是函数契约，不是文件权限安全隔离；评测真值与输入共同保存在原始证据文件中供复核。

重跑 `run` 会重算廉价审计并检查已存结果相同，原始cost保留；它仍打印历史已拒绝的区间，因此解释结果应以 `metric_audit.json`和报告为准。`freeze`只用于新实验目录，不应覆盖现有协议。任何数据或源代码修改触发拒绝。

未来新实验必须新目录和新协议，不能改变当前污染seed/严重程度/预算以追正结果。自动修复未实现、未评测，真实人工审核未完成，用户理解未验证。


## 开发诊断 v2（无下载、无新推理）

在仓库根目录运行：

```bash
uv sync --locked --python 3.12
uv run python scripts/diagnose_v2.py verify
uv run python scripts/correct_control_v2.py verify
uv run python scripts/summarize_diagnosis_v2.py --verify
uv run pytest -q
uv run streamlit run dashboard.py
```

`verify`从reference逐图重算，不能使用`freeze`覆盖现有协议。正式历史运行顺序为：diagnose → freeze → 提交cd4bc9f → run --limit 1 → run → verify；发现随机对照问题后，correct_control_v2.py freeze → 提交db7f617 → run。初次错误组假设与无效随机结果保留。不要重复freeze以刷新成本；协议/代码/模型身份变化会被拒绝，应新建版本。

可选本机源数据核验（需已有上游图像、标签、预测、权重）：

```bash
uv run python scripts/verify_source_v2.py --upstream /path/to/driving-data-engine
```

原始逐图诊断在development.json；冻结在protocol.json；三seed全量观测/注入truth/候选/误报ID在runs；独立随机对照在control_correction；presentation.json只由原始记录派生。旧result中的random已失效，UI读取纠正后random。原结果主比较未变。

故障注入测试模拟首个原子记录后中断并恢复、残缺临时文件、缓存篡改和身份漂移，测试写临时目录，不更改公开证据。单写者协议，不宣称多worker并发支持。CI使用缓存做确定性回放；完整源图和权重核验仅在本机执行，不能把它说成CI重新推理。

## 真实评测准备 v3

运行 `uv run python scripts/readiness_v3.py verify` 核验保留清单。详细范围、原始提交门禁和未来评分命令见[资格报告](READINESS_V3.md)。此阶段不生成真实错误指标。
