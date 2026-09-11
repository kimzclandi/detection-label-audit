from pathlib import Path

import pandas as pd
import streamlit as st

from label_audit import read

ROOT = Path(__file__).resolve().parent
st.title("检测标签质量审计")
st.caption("固定复核图数预算 · 合成污染与真实待复核分开 · 无自动修复")
r = read(ROOT / "reports/result.json")
fix = read(ROOT / "reports/metric_audit.json")
st.warning("100%命中率只属于人工注入的重复/坐标错误；没有独立人工裁决的真实标签效果。")
view = st.selectbox(
    "证据类型", ["可控合成污染", "原始标签：待复核", "开发诊断 v2：探索性", "定位归因 v4：事后诊断"]
)
if view == "可控合成污染":
    budget = st.selectbox("复核图数预算", [12, 24])
    df = pd.DataFrame(r["records"])
    df = df[df.budget_images == budget]
    st.dataframe(df.groupby("method")[["precision_at_budget", "recall", "hits", "budget_images"]].mean())
    st.write(f"组合 − 几何规则 · 主预算差：{fix['primary_delta']:.1%}。该污染设计不支持模型项的增量价值。")
    st.caption("原版固定名单区间已拒绝；预算保持重采样为事后统计修复，详见报告。")
    st.dataframe(
        [
            {"seed": x["seed"], "method": x["method"], "type": t, **v}
            for x in r["records"]
            if x["budget_images"] == budget
            for t, v in x["by_type"].items()
        ]
    )
elif view == "原始标签：待复核":
    q = read(ROOT / "reports/real_pending.json")
    byid = {x["id"]: x for x in q["candidates"]}
    sid = st.selectbox("问题候选", q["review_order"])
    st.info("状态：pending_review。模型错误、原标签错误和语义映射差异尚未区分。")
    st.json(byid[sid])
elif view == "开发诊断 v2：探索性":
    diagnosis = read(ROOT / "reports/diagnosis_v2/development.json")
    presentation = read(ROOT / "reports/diagnosis_v2/presentation.json")
    st.warning("36图 / 35来源组，已看过的开发数据。仅合成污染结果；随机对照经事后协议纠正。")
    st.dataframe(presentation["table"])
    st.json(presentation["primary"])
    st.caption("每种错误跨3次污染support=18，但只有35个来源组；不能当作独立样本。")
    st.json(diagnosis["summary"]["counts"])
    st.dataframe(diagnosis["summary"]["coverage"])
    st.caption("coverage是与原始参考标签的一对一匹配，不能解释为真实标签错误检测准确率。")
    sid = st.selectbox("开发图证据", [r["id"] for r in diagnosis["records"]])
    st.json(next(r for r in diagnosis["records"] if r["id"] == sid))
    st.write("CPU审计秒数", presentation["cpu_seconds"])
    st.info("决策：保留guard供探索性候选清理；拒绝真实准确率、人工时间或训练收益主张。")
else:
    localization = read(ROOT / "reports/localization_v4/result.json")
    st.warning("选中污染图不等于定位注入错误。以下为已有开发集合成结果的事后归因，不是真实标签准确率。")
    st.dataframe(localization["summary"])
    st.caption(
        "selected_localized_images：满足类型、目标索引、原类别/IoU及还原后消失条件；分母24为3次×8图预算。"
    )
    cases = [r for r in localization["records"] if r["selected"]]
    index = st.selectbox(
        "逐例归因",
        range(len(cases)),
        format_func=lambda i: f"{cases[i]['method']} / {cases[i]['seed']} / {cases[i]['id']}",
    )
    trace = cases[index]
    st.json(trace)
    run = read(ROOT / f"reports/diagnosis_v2/runs/s{trace['seed']}.json")
    key = "guarded_candidates" if trace["method"] == "guarded" else "old_candidates"
    st.json(
        {
            "injection": run["changes"].get(trace["id"]),
            "candidate": next(r for r in run[key] if r["id"] == trace["id"]),
            "observed": next(r for r in run["observed"] if r["id"] == trace["id"]),
        }
    )
with st.expander("协议与统计修复"):
    st.json(read(ROOT / "reports/protocol.json"))
    st.json(fix)

feedback_path = ROOT / "reports/human_feedback_v1/result.json"
if feedback_path.exists():
    st.subheader("人工批量反馈 · 探索性")
    st.warning("A本人确认、B由用户转述：40张均未发现明确错误。缺少逐图提交，非正式金标准；不能排除共同漏检。")
    feedback = read(feedback_path)
    st.json(feedback)

with st.expander("真实评测准备 v3 · 尚未评分"):
    readiness = read(ROOT / "reports/readiness_v3/ledger.json")
    st.write("保留图片数", readiness["reserved_images"])
    st.write("保留来源组数", readiness["reserved_groups"])
    st.warning("曾用于上游检测测试，仅对当前标签审计诊断隔离；缺少新的逐图裁决，真实错误指标未定义。")
    st.json({"status": readiness["status"], "real_error_metrics": readiness["real_error_metrics"]})
