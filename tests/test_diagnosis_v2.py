import copy
import importlib.util
import random
from pathlib import Path

import pytest

from audit_diagnosis import diagnose, explained_elsewhere, guarded, validate
from label_audit import audit, observed, read

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scene():
    return {
        "id": "a",
        "group": "shared",
        "width": 100,
        "height": 100,
        "labels": [{"box": [10, 10, 50, 50], "label": 3}, {"box": [40, 10, 80, 50], "label": 3}],
        "predictions": [{"box": [10, 10, 50, 50], "label": 3, "score": 0.9}],
    }


def test_cross_object_guard_and_preserve_input():
    row = scene()
    before = copy.deepcopy(row)
    assert audit(row)["combined_score"] > 0
    assert guarded(row)["combined_score"] == 0
    assert len(guarded(row)["suppressed"]) == 1
    assert row == before


def test_real_offset_and_missing_are_not_silently_dropped():
    row = scene()
    row["labels"].pop(0)
    assert guarded(row)["combined_score"] == audit(row)["combined_score"] > 0
    row["labels"] = []
    assert guarded(row)["evidence"][0]["type"] == "missing_candidate"
    assert guarded(row)["combined_score"] == 0.9


def test_class_conflict_and_geometry_preserved():
    row = scene()
    row["labels"][0]["label"] = 1
    assert any(e["type"] == "class_candidate" for e in guarded(row)["evidence"])
    row["labels"].append(copy.deepcopy(row["labels"][0]))
    assert guarded(row)["geometry_score"] == 10


def test_unique_matching_and_shared_group_retained():
    row = scene()
    row["labels"].append(copy.deepcopy(row["labels"][0]))
    d = diagnose(row)
    assert len(d["reference_matches"]) == 1
    assert d["multi_label_predictions"] == [0]
    second = copy.deepcopy(row)
    second["id"] = "b"
    validate([row, second])
    with pytest.raises(ValueError, match="Duplicate"):
        validate([row, row])


@pytest.mark.parametrize("failure", ["nan", "shape", "missing_predictions", "confidence"])
def test_invalid_inputs_fail_without_silent_filter(failure):
    row = scene()
    if failure == "nan":
        row["labels"][0]["box"][0] = float("nan")
    elif failure == "shape":
        row["predictions"][0]["box"] = [1, 2]
    elif failure == "missing_predictions":
        del row["predictions"]
    else:
        row["predictions"][0]["score"] = 1.5
    with pytest.raises((ValueError, KeyError)):
        validate([row])


def test_interrupted_write_resume_idempotency_and_drift(tmp_path, monkeypatch):
    engine = load_script("diagnose_v2")
    engine.save(tmp_path / "protocol.json", read(engine.OUT / "protocol.json"))
    original = engine.save
    state = {"raised": False}

    def interrupted(path, value):
        original(path, value)
        if path.parent.name == "runs" and not state["raised"]:
            state["raised"] = True
            raise InterruptedError("injected process interruption after first atomic record")

    monkeypatch.setattr(engine, "save", interrupted)
    with pytest.raises(InterruptedError):
        engine.run(tmp_path)
    first = next((tmp_path / "runs").glob("*.json"))
    before = first.read_bytes()
    monkeypatch.setattr(engine, "save", original)
    (tmp_path / "runs/s911213.partial").write_text("{truncated")
    engine.run(tmp_path)
    engine.run(tmp_path, verify=True)
    assert first.read_bytes() == before
    assert not (tmp_path / "runs/s911213.partial").exists()
    monkeypatch.setattr(engine, "identity", lambda: {"model": "changed"})
    with pytest.raises(ValueError, match="identity drift"):
        engine.run(tmp_path)


def test_cache_content_drift_rejected(tmp_path):
    engine = load_script("diagnose_v2")
    p = tmp_path / "cached.json"
    engine.save(p, {"value": 1})
    with pytest.raises(ValueError, match="drift"):
        engine.save(p, {"value": 2})


def test_random_control_domain_separation_and_old_failure():
    correction = load_script("correct_control_v2")
    ids = [str(i) for i in range(36)]
    # Reproduce algorithm coupling: sample half and shuffle with the same seed.
    hits = []
    for seed in range(100):
        polluted = set(random.Random(seed).sample(sorted(ids), 18))
        coupled = sorted(ids)
        random.Random(seed).shuffle(coupled)
        assert not set(coupled[:8]) & polluted
        order = correction.independent_order(ids, seed)
        assert order == correction.independent_order(list(reversed(ids)), seed)
        hits.append(len(set(order[:8]) & polluted))
    assert 3 < sum(hits) / len(hits) < 5


def test_frozen_sources_and_historical_evidence_intact():
    from label_audit import file_hash

    p = read(ROOT / "reports/diagnosis_v2/provenance.json")
    assert p["checkpoint_verified"]
    for name, sha in p["historical_evidence_hashes"].items():
        assert file_hash(ROOT / name) == sha
    ref = read(ROOT / "reports/reference.json")["rows"]
    dev = {r["group"] for r in ref if r["split"] == "dev"}
    old = {r["group"] for r in ref if r["split"] == "eval"}
    assert len(dev) == 35 and not dev & old


def test_diagnostic_summary_recomputed():
    from audit_diagnosis import summarize

    rows = sorted(
        [r for r in read(ROOT / "reports/reference.json")["rows"] if r["split"] == "dev"],
        key=lambda r: r["id"],
    )
    d = read(ROOT / "reports/diagnosis_v2/development.json")
    assert summarize(rows, d["records"]) == d["summary"]
    for row, record in zip(rows, d["records"], strict=True):
        assert record == diagnose(row)
        assert all(explained_elsewhere(observed(row), e) for e in record["guarded"]["suppressed"])
