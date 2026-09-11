"""Synthetic fixtures below are software tests, never human evidence."""

import copy
import importlib.util
from pathlib import Path

import pytest

from label_audit import digest, read

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("readiness_v3", ROOT / "scripts/readiness_v3.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sample(sid, group, split):
    return {
        "sample_id": sid,
        "group_id": group,
        "split": split,
        "sha256": "image",
        "labels_sha256": "canonical",
    }


def test_group_leakage_excluded_even_when_id_differs():
    source = [
        sample("a", "dev", "test"),
        sample("b", "train", "seed"),
        sample("c", "train", "test"),
        sample("d", "new", "test"),
        sample("e", "pool", "pool"),
    ]
    result = module.ledger(source, [{"group": "dev"}])
    assert result["reserved_ids"] == ["d"]
    assert result["real_error_metrics"] is None
    assert not result["rows"][3]["never_used_upstream"]


def test_duplicate_ids_and_same_group_candidates_refused():
    with pytest.raises(ValueError, match="Duplicate"):
        module.ledger([sample("a", "a", "test")] * 2, [])
    with pytest.raises(ValueError, match="one image"):
        module.ledger([sample("a", "x", "test"), sample("b", "x", "test")], [])


def fixtures():
    manifest = {"cases": [{"case_id": "unit", "width": 100, "height": 100}], "budget_images": 1}

    def submission(role):
        return {
            "protocol": digest(manifest),
            "role": role,
            "human_attestation": True,
            "independent_attestation": True,
            "submitted_utc": "2026-09-11T00:00:00Z",
            "reviewer_id": "SYNTHETIC_TEST_" + role,
            "answers": [
                {
                    "case_id": "unit",
                    "verdict": "no_error_found",
                    "reason": "Synthetic software test fixture only",
                    "issues": [],
                }
            ],
        }

    return manifest, submission("A"), submission("B"), {"guarded": ["unit"]}


def test_missing_and_bulk_feedback_cannot_create_scores():
    m, a, b, orders = fixtures()
    with pytest.raises(ValueError, match="Missing"):
        module.score_from_submissions(m, None, None, None, orders)
    with pytest.raises((KeyError, ValueError)):
        module.score_from_submissions(m, {"basis": "bulk"}, b, None, orders)
    a["answers"] = []
    with pytest.raises(ValueError, match="Incomplete"):
        module.score_from_submissions(m, a, b, None, orders)


def test_same_reviewer_rejected():
    m, a, b, orders = fixtures()
    b["reviewer_id"] = a["reviewer_id"]
    with pytest.raises(ValueError, match="distinct"):
        module.score_from_submissions(m, a, b, None, orders)


def test_positive_requires_arbitration_and_unresolved_not_dropped():
    m, a, b, orders = fixtures()
    a["answers"][0].update(
        verdict="label_error",
        issues=[{"type": "box", "region": [1, 1, 10, 10], "reason": "Synthetic unit localization issue"}],
    )
    with pytest.raises(ValueError, match="Incomplete"):
        module.score_from_submissions(m, a, b, None, orders)
    c = copy.deepcopy(a)
    c.update(role="C", reviewer_id="SYNTHETIC_TEST_C")
    scores = module.score_from_submissions(m, a, b, c, orders)
    assert scores["scores"]["guarded"]["hits"] == 1
    c["answers"][0].update(verdict="unresolved", issues=[])
    with pytest.raises(ValueError, match="Incomplete"):
        module.score_from_submissions(m, a, b, c, orders)


def test_all_negative_recall_undefined():
    m, a, b, orders = fixtures()
    scores = module.score_from_submissions(m, a, b, None, orders)["scores"]["guarded"]
    assert scores["recall"] is None and scores["precision_at_budget"] == 0
    with pytest.raises(ValueError, match="every case"):
        module.score_from_submissions(m, a, b, None, {"guarded": []})


def test_snapshot_and_freeze_are_replayed():
    manifest = module.verify()
    assert len(manifest["cases"]) == 59
    assert len({c["group"] for c in manifest["cases"]}) == 59
    snapshot = read(module.OUT / "source_snapshot.json")
    source = {r["sample_id"]: r for r in snapshot["upstream_manifest_rows"]}
    for c in manifest["cases"]:
        assert digest(c["labels"]) == source[c["source_id"]]["labels_sha256"]
    assert len(snapshot["local_image_ids"]) == 360


def test_identity_drift_refuses(monkeypatch):
    monkeypatch.setattr(module, "identity", lambda: {"changed": True})
    with pytest.raises(ValueError, match="identity drift"):
        module.verify()
