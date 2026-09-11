from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_synthetic_and_pending_views():
    app = AppTest.from_file(str(Path(__file__).parents[1] / "dashboard.py")).run(timeout=30)
    assert not app.exception and len(app.dataframe) == 2
    app.selectbox[0].select("原始标签：待复核").run(timeout=30)
    assert not app.exception and "pending_review" in app.info[0].value


def test_development_diagnosis_view():
    app = AppTest.from_file(str(Path(__file__).parents[1] / "dashboard.py")).run(timeout=30)
    app.selectbox[0].select("开发诊断 v2：探索性").run(timeout=30)
    assert not app.exception
    assert len(app.dataframe) == 2
    assert "35来源组" in app.warning[1].value
