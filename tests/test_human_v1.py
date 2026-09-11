import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("human_core", Path(__file__).parents[1] / "human_v1/core.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def manifest():
    return {"cases": [{"case_id": "one", "width": 100, "height": 100}]}


def submission(role, name, verdict="no_error_found", issues=None):
    return {
        "role": role,
        "reviewer_id": name,
        "protocol": m.digest(manifest()),
        "human_attestation": True,
        "independent_attestation": True,
        "submitted_utc": "test-only-fixture",
        "answers": [
            {
                "case_id": "one",
                "verdict": verdict,
                "reason": "Unit test fixture, never a real human judgment",
                "issues": issues or [],
            }
        ],
    }


def issue():
    return {"type": "missing", "region": [1, 1, 50, 50], "reason": "Unit test localization evidence only"}


def test_cannot_score_before_human_completion():
    with pytest.raises(ValueError, match="Incomplete"):
        m.evaluate(manifest(), {"status": "pending_humans", "pending": [{}]}, {"random": ["one"]}, 1)
    a = submission("A", "person1")
    b = submission("B", "person2")
    b["answers"] = []
    result = m.reconcile(manifest(), a, b)
    assert result["gold"] == [] and result["status"] == "pending_humans"


def test_same_reviewer_or_no_attestation_rejected():
    with pytest.raises(ValueError, match="distinct"):
        m.reconcile(manifest(), submission("A", "Same"), submission("B", "same"))
    a = submission("A", "a")
    a["human_attestation"] = False
    with pytest.raises(ValueError, match="human"):
        m.reconcile(manifest(), a, submission("B", "b"))


def test_even_agreed_positives_require_third_person():
    a = submission("A", "a", "label_error", [issue()])
    b = submission("B", "b", "label_error", [issue()])
    assert m.reconcile(manifest(), a, b)["status"] == "pending_humans"
    with pytest.raises(ValueError, match="third"):
        m.reconcile(manifest(), a, b, submission("C", "a", "label_error", [issue()]))
    done = m.reconcile(manifest(), a, b, submission("C", "c", "label_error", [issue()]))
    assert done["status"] == "ready"
    assert m.evaluate(manifest(), done, {"random": ["one"]}, 1)["random"]["precision_at_budget"] == 1


def test_unresolved_retained_and_invalid_region_rejected():
    a = submission("A", "a", "label_error", [issue()])
    b = submission("B", "b")
    assert m.reconcile(manifest(), a, b, submission("C", "c", "unresolved"))["status"] == "pending_humans"
    bad = issue()
    bad["region"] = [0, 0, 101, 20]
    with pytest.raises(ValueError, match="outside"):
        m.validate_submission(submission("A", "a", "label_error", [bad]), manifest(), "A")


def test_no_error_consensus_not_fake_kappa_or_missing_denominator():
    result = m.reconcile(manifest(), submission("A", "a"), submission("B", "b"))
    assert result["cohen_kappa"] is None and result["agreement"] == 1
    with pytest.raises(ValueError, match="exactly"):
        m.evaluate(manifest(), result, {"random": ["one", "one"]}, 1)


def test_frozen_source_drift_rejected(tmp_path):
    path = tmp_path / "reports/human_v1"
    path.mkdir(parents=True)
    (tmp_path / "code.py").write_text("changed")
    m.immutable(path / "freeze.json", {"files": {"code.py": "wrong"}})
    with pytest.raises(ValueError, match="drift"):
        m.verify_frozen(tmp_path)
