# 真实标签独立人工裁决基准 v1

状态：已冻结、待真实人工复核。40张图，0条真实人工提交，0张金标准；目前不能报告真实标签错误 precision/recall。

## 设计与边界

从既有120个独立图像组中，按预定哈希均匀选40组。抽样不依据模型分数或标签问题线索。评测随机、几何规则、组合方法在这40张图内的排序，主预算8张；排序在人工提交前冻结。该评测仅覆盖这个子集，不能解释为全120张的precision，也不是新的检测器泛化测试。

A、B为两名不同真人，各检查全部40张原图和现有框，次序不同，不看算法输出或彼此答案，不用AI代判。全部阳性、分歧和不确定样本由第三名真人C重新查看并裁决；A/B一致阴性作为双人共识参考，仍可能共享漏检。人员自我声明与不同代号是流程约束，不是身份认证或独立性证明。

范围是七类派生标注（person包括rider），不能把类别映射差异直接宣称为BDD原始标签错误。问题类型包括漏标、类别错误、框定位/尺度、重复及管线错误。每个阳性需局部区域及解释；不清晰、遮挡或规范含糊时保留不确定。单靠图像通常无法归因到管线错误，须附映射或源记录证据。

## 交付复核者

分别把reviewer-A.zip和reviewer-B.zip交给两位复核者，不交协调者映射、公开排名或对方答案。解压，阅读REVIEW_GUIDE.md，打开review.html。先保存本图判断，再切图；定期导出草稿备份。浏览器本地存储可能被清除，JSON备份是跨浏览器恢复依据。最终各导出本人提交JSON。不得由同一人换代号完成两轮。

若file页面的本地存储受浏览器限制，可在各自解压目录运行：

```bash
python3 -m http.server 8525 --bind 127.0.0.1
```

打开 http://127.0.0.1:8525/review.html 。每人使用自己的目录及浏览器配置。

## 协调者复现

以下命令在仓库根目录运行。A.json/B.json/C.json必须来自实际真人，不能用测试夹具或AI回答代替。OUTPUT为独立输出目录，不覆盖旧证据。

```bash
uv sync --locked --python 3.12
uv run pytest -q
PYTHONPATH=src:human_v1 uv run python human_v1/prepare.py --images /ABS/PATH/BDD_IMAGES --output /ABS/PATH/PACKETS
uv run python human_v1/manage.py reconcile --a /ABS/A.json --b /ABS/B.json --output /ABS/OUTPUT/round1.json --packet-root /ABS/PATH/PACKETS
# 把生成的reviewer-C目录交第三人；收到真实提交后：
uv run python human_v1/manage.py score --a /ABS/A.json --b /ABS/B.json --c /ABS/C.json --output /ABS/OUTPUT/final.json
```

若没有任何待裁决样本，可省略--c。已有C目录会拒绝覆盖，重新组织一轮前须保留旧包，并把原reviewer-A图像复制到新的packet-root。提交摘要记录在结果中；输入身份、协议、冻结文件漂移或未完成裁决会拒绝计分。部分提交可登记但不能形成完整基准；不确定案例不得删除以改变分母。

## 尚未验证

当前仅冻结图像级precision@8与recall，以及原始一致率/Cohen kappa；一致率不是准确率。待真人完成后还需审查裁决理由和证据，按错误类型整理结果及误报案例，并明确任何后续统计属于事后分析。未验证自动修复、训练收益、人工降本或生产规模。这个40图试点不足以稳定比较罕见错误。

实现为AI辅助，AI未承担任何实际人工裁决。用户尚未通过理解验证。必须能解释core.py中的validate_submission、reconcile、evaluate、verify_frozen及其失败条件。

## 主动回忆（暂不附答案）

1. 为什么先固定40张，再比较三种排序？
2. 双人一致阴性为何仍不是绝对真值？
3. 为什么两人一致阳性还安排第三人？
4. 什么情况下框差异不能算标注错误？
5. person/rider映射如何制造假阳性？
6. 为什么不确定案例不能从分母删除？
7. 子集precision@8为何不能外推全池precision？
8. 同一人换代号为何破坏独立裁决？
9. kappa高是否证明裁决正确？
10. 若真实错误很少，应如何限制方法优劣结论？
