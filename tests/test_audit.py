import copy

import pytest

from label_audit import audit, digest, immutable, inject, metrics, rank


def row(i=0):
    return {
        "id": str(i),
        "group": str(i),
        "width": 100,
        "height": 100,
        "labels": [{"box": [10.0, 10.0, 50.0, 50.0], "label": 3}],
        "predictions": [{"box": [10.0, 10.0, 50.0, 50.0], "label": 3, "score": 0.9}],
    }


def test_truth_never_accepted_by_auditor():
    r = row()
    r["truth"] = "missing"
    with pytest.raises(ValueError, match="truth"):
        audit(r)


def test_controlled_injection_and_no_reference_mutation():
    rows = [row(i) for i in range(20)]
    before = digest(rows)
    obs, truth, changes = inject(rows, 11)
    assert digest(rows) == before and len(truth) == 10
    assert set(truth.values()) == {"missing", "class", "box", "duplicate", "pipeline"}
    assert all(list(truth.values()).count(t) == 2 for t in set(truth.values()))
    assert (obs, truth, changes) == inject(rows, 11)
    assert all(audit(r)["status"] == "pending_review" for r in obs)


def test_duplicate_and_coordinate_mapping_are_distinct_from_model_truth():
    r = row()
    r["labels"].append(copy.deepcopy(r["labels"][0]))
    assert audit(r)["geometry_score"] == 10
    r = row()
    r["labels"][0]["box"] = [0.1, 0.1, 0.5, 0.5]
    assert audit(r)["geometry_score"] == 10
    r = row()
    r["labels"][0]["label"] = 99
    assert audit(r)["geometry_score"] == 20
    r = row()
    r["labels"][0]["box"] = [float("nan"), 0, 1, 1]
    assert audit(r)["geometry_score"] == 20


def test_high_confidence_false_positive_stays_pending():
    r = row()
    r["labels"] = []
    a = audit(r)
    assert a["combined_score"] == 0.9
    assert a["evidence"][0]["type"] == "missing_candidate"
    assert a["status"] == "pending_review"


def test_review_denominator_and_immutable(tmp_path):
    m = metrics(["a", "b", "c"], {"a": "missing", "c": "box"}, 2)
    assert m["precision_at_budget"] == 0.5 and m["recall"] == 0.5
    assert m["by_type"]["missing"]["recall"] == 1
    assert m["by_type"]["box"]["recall"] == 0
    with pytest.raises(ValueError):
        metrics(["a", "a"], {"a": "box"}, 2)
    path = tmp_path / "r.json"
    immutable(path, m)
    immutable(path, m)
    with pytest.raises(ValueError):
        immutable(path, {"bad": 1})


def test_deterministic_ties():
    records = [audit(row(i)) for i in range(20)]
    for method in ("random", "geometry", "combined"):
        assert rank(records, method, 101) == rank(records, method, 101)
        assert len(set(rank(records, method, 101))) == 20
