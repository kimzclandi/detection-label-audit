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
view = st.selectbox("证据类型", ["可控合成污染", "原始标签：待复核"])
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
else:
    q = read(ROOT / "reports/real_pending.json")
    byid = {x["id"]: x for x in q["candidates"]}
    sid = st.selectbox("问题候选", q["review_order"])
    st.info("状态：pending_review。模型错误、原标签错误和语义映射差异尚未区分。")
    st.json(byid[sid])
with st.expander("协议与统计修复"):
    st.json(read(ROOT / "reports/protocol.json"))
    st.json(fix)
