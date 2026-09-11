"""Recompute exploratory metrics from attributed bulk human feedback, not signed submissions."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "human_v1"))
from core import digest, immutable, read, verify_frozen  # noqa: E402


def recompute():
    manifest = verify_frozen(ROOT)
    feedback = read(ROOT / "reports/human_feedback_v1/intake.json")
    orders = read(ROOT / "reports/human_v1/orders.json")
    if feedback["protocol"] != digest(manifest) or orders["protocol"] != digest(manifest):
        raise ValueError("Protocol mismatch")
    if feedback["basis"] != "retrospective_bulk_confirmation_via_conversation":
        raise ValueError("Unexpected evidence basis")
    ids = {c["case_id"] for c in manifest["cases"]}
    if len(ids) != 40 or feedback["reported_case_ids"] != [c["case_id"] for c in manifest["cases"]]:
        raise ValueError("Coverage mismatch")
    for role in ("A", "B"):
        r = feedback["reviewers"][role]
        if r["reported_verdict"] != "no_error_found" or not r["independence_reported"]:
            raise ValueError("This calculation applies only to reported all-negative independent reviews")
    scores = {}
    for method, order in orders["orders"].items():
        if len(order) != 40 or set(order) != ids:
            raise ValueError("Ranking mismatch")
        scores[method] = {
            "budget": 8,
            "reported_error_hits": 0,
            "precision_at_8_against_reported_consensus": 0.0,
            "recall": None,
        }
    return {
        "protocol": digest(manifest),
        "feedback_sha256": digest(feedback),
        "status": "exploratory_reported_consensus_not_formal_gold",
        "images": 40,
        "reported_positive_images": 0,
        "formal_gold_cases": 0,
        "metrics": scores,
        "reported_agreement": 1.0,
        "cohen_kappa": None,
        "undefined_reason": "Recall denominator is zero; kappa expected agreement is one.",
        "arbitration": "No reported positive, disagreement or unresolved case triggers C; shared missed errors remain possible.",
        "decision": "No evidence to distinguish mining policies. Do not infer error-free labels or model improvement.",
    }


if __name__ == "__main__":
    result = recompute()
    immutable(ROOT / "reports/human_feedback_v1/result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
