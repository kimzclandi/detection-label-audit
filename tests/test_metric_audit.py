import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("metric_audit", Path(__file__).parents[1] / "metric_audit.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_bootstrap_reranks_copies_and_keeps_budget():
    # The original hit-only resampling would count three hits over a budget of two.
    assert m.reranked_precision(["a", "b"], {"a": "duplicate"}, ["a", "a", "a", "b"], 2) == 1
    assert m.reranked_precision(["a", "b"], {"a": "duplicate"}, ["b", "b", "b", "b"], 2) == 0
    with pytest.raises(ValueError):
        m.reranked_precision(["a"], {}, ["a"], 2)
