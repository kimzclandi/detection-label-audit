"""Counterexamples for injection attribution, not human annotations."""

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

from label_audit import audit, read

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("localization_v4", ROOT / "scripts/localization_v4.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def scene():
    clean = {
        "id": "unit",
        "group": "unit",
        "width": 100,
        "height": 100,
        "labels": [{"box": [10, 10, 50, 50], "label": 3}],
        "predictions": [{"box": [10, 10, 50, 50], "label": 3, "score": 0.9}],
    }
    row = copy.deepcopy(clean)
    row["labels"][0]["box"] = [20, 20, 40, 40]
    change = {"type": "box", "label_index": 0, "before": copy.deepcopy(clean["labels"][0])}
    return clean, row, change


def evaluate(clean, row, change):
    return module.attribution(row, clean, change, audit(row), audit(clean))


def test_correct_box_localization_and_undo():
    clean, row, change = scene()
    r = evaluate(clean, row, change)
    assert r["localized"] and r["all_max_evidence_localized"] and r["score_rises_after_injection"]


def test_distractor_can_dominate_true_localization():
    clean, row, change = scene()
    distractor = {"box": [70, 70, 90, 90], "label": 3, "score": 0.99}
    clean["predictions"].append(distractor)
    row["predictions"].append(distractor)
    r = evaluate(clean, row, change)
    assert r["localized"] and not r["localized_at_max"] and not r["score_rises_after_injection"]


def test_same_image_wrong_label_is_not_target_localization():
    clean, row, change = scene()
    candidate = audit(row)
    candidate["evidence"][0]["label_index"] = 1
    assert not module.attribution(row, clean, change, candidate, audit(clean))["localized"]


def test_reference_class_and_iou_are_required():
    clean, row, change = scene()
    candidate = audit(row)
    for p in [
        {"box": [10, 10, 50, 50], "label": 1, "score": 0.9},
        {"box": [60, 60, 80, 80], "label": 3, "score": 0.9},
    ]:
        wrong = copy.deepcopy(row)
        wrong["predictions"] = [p]
        assert not module.attribution(wrong, clean, change, candidate, audit(clean))["localized"]


def test_existing_candidate_cannot_be_credited_to_injection():
    clean, row, change = scene()
    candidate = audit(row)
    assert not module.attribution(row, clean, change, candidate, candidate)["localized"]


def test_missing_has_no_label_index_and_class_repair_targets_original_class():
    clean, row, change = scene()
    row["labels"] = []
    change["type"] = "missing"
    assert evaluate(clean, row, change)["localized"]
    row = copy.deepcopy(clean)
    row["labels"][0]["label"] = 1
    change["type"] = "class"
    assert evaluate(clean, row, change)["localized"]


def test_max_ties_do_not_claim_unique_causal_winner():
    clean, row, change = scene()
    candidate = audit(row)
    score = candidate["evidence"][0]["score"]
    candidate["evidence"].append({"type": "missing_candidate", "prediction_index": 0, "score": score})
    result = module.attribution(row, clean, change, candidate, audit(clean))
    assert result["localized_at_max"] and not result["all_max_evidence_localized"]


def test_frozen_replay_and_unchanged_localizable_set():
    result = module.build()
    assert result == read(module.OUT / "result.json")
    sets = {
        m: {(r["seed"], r["id"]) for r in result["records"] if r["method"] == m and r["localized"]}
        for m in ["combined", "guarded"]
    }
    assert sets["combined"] == sets["guarded"]
    assert len(result["records"]) == 216


def test_identity_drift_rejected(monkeypatch):
    monkeypatch.setattr(module, "identity", lambda: {"changed": True})
    with pytest.raises(ValueError, match="identity drift"):
        module.build()
