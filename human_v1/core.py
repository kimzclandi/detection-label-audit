"""Human-only annotation adjudication contracts; no inferred human judgments."""

import hashlib
import json
import math
from pathlib import Path

VERDICTS = {"no_error_found", "label_error", "unresolved"}
TYPES = {"missing", "class", "box", "duplicate", "pipeline"}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def immutable(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if read(path) != value:
            raise ValueError("Immutable artifact drift")
    else:
        with path.open("x") as file:
            json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)
            file.write("\n")


def validate_answer(answer, case):
    if (
        answer["verdict"] not in VERDICTS
        or not isinstance(answer["reason"], str)
        or len(answer["reason"].strip()) < 10
    ):
        raise ValueError("Verdict and substantive reason required")
    issues = answer["issues"]
    if not isinstance(issues, list):
        raise ValueError("Issue list required")
    if answer["verdict"] == "label_error" and not issues:
        raise ValueError("Positive verdict needs localized evidence")
    if answer["verdict"] == "no_error_found" and issues:
        raise ValueError("Negative verdict cannot contain confirmed issues")
    for issue in issues:
        if issue["type"] not in TYPES or len(issue["reason"].strip()) < 10:
            raise ValueError("Issue type and reason required")
        box = issue["region"]
        if len(box) != 4 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in box):
            raise ValueError("Finite pixel region required")
        x1, y1, x2, y2 = box
        if not (0 <= x1 < x2 <= case["width"] and 0 <= y1 < y2 <= case["height"]):
            raise ValueError("Region outside original image")


def validate_submission(submission, manifest, role):
    if submission["protocol"] != digest(manifest) or submission["role"] != role:
        raise ValueError("Protocol or role drift")
    if submission.get("human_attestation") is not True or not submission.get("reviewer_id", "").strip():
        raise ValueError("Named human attestation required")
    if not submission.get("independent_attestation") or not submission.get("submitted_utc"):
        raise ValueError("Independent review attestation required")
    cases = {r["case_id"]: r for r in manifest["cases"]}
    answers = submission["answers"]
    if len({r["case_id"] for r in answers}) != len(answers):
        raise ValueError("Duplicate answers")
    for answer in answers:
        if answer["case_id"] not in cases:
            raise ValueError("Unknown case")
        validate_answer(answer, cases[answer["case_id"]])
    return {r["case_id"]: r for r in answers}


def reconcile(manifest, first, second, arbitration=None):
    a = validate_submission(first, manifest, "A")
    b = validate_submission(second, manifest, "B")
    if first["reviewer_id"].strip().casefold() == second["reviewer_id"].strip().casefold():
        raise ValueError("Independent reviewers must be distinct people")
    arb = {}
    if arbitration is not None:
        arb = validate_submission(arbitration, manifest, "C")
        if arbitration["reviewer_id"].strip().casefold() in {
            first["reviewer_id"].strip().casefold(),
            second["reviewer_id"].strip().casefold(),
        }:
            raise ValueError("Arbiter must be a third person")
    gold, pending, paired = [], [], []
    for case in manifest["cases"]:
        cid = case["case_id"]
        if cid not in a or cid not in b:
            pending.append({"case_id": cid, "status": "missing_independent_review"})
            continue
        paired.append((a[cid]["verdict"], b[cid]["verdict"]))
        if a[cid]["verdict"] == b[cid]["verdict"] == "no_error_found":
            gold.append(
                {
                    "case_id": cid,
                    "verdict": "no_error_found",
                    "issues": [],
                    "basis": "two_independent_negative_reviews",
                }
            )
        elif cid not in arb:
            pending.append({"case_id": cid, "status": "needs_third_person", "reviews": [a[cid], b[cid]]})
        elif arb[cid]["verdict"] == "unresolved":
            pending.append({"case_id": cid, "status": "unresolved_after_arbitration"})
        else:
            gold.append(
                {
                    "case_id": cid,
                    "verdict": arb[cid]["verdict"],
                    "issues": arb[cid]["issues"],
                    "basis": "third_person_adjudication",
                }
            )
    n = len(paired)
    agreement = sum(x == y for x, y in paired) / n if n else None
    expected = (
        sum(sum(x == v for x, _ in paired) * sum(y == v for _, y in paired) for v in VERDICTS) / n**2
        if n
        else None
    )
    kappa = (agreement - expected) / (1 - expected) if n and expected < 1 else None
    return {
        "status": "ready" if not pending else "pending_humans",
        "gold": gold,
        "pending": pending,
        "paired_reviews": n,
        "agreement": agreement,
        "cohen_kappa": kappa,
        "note": "Agreement is not accuracy. Self-attestations are not identity verification. Negative consensus means no error found, not guaranteed complete labels.",
    }


def evaluate(manifest, adjudicated, orders, budget=8):
    if adjudicated["status"] != "ready" or adjudicated["pending"]:
        raise ValueError("Incomplete or unresolved adjudication: no benchmark scores")
    ids = {r["case_id"] for r in manifest["cases"]}
    gold = {r["case_id"]: r for r in adjudicated["gold"]}
    if set(gold) != ids or not 0 < budget <= len(ids):
        raise ValueError("Gold coverage or review budget mismatch")
    positives = {cid for cid, g in gold.items() if g["verdict"] == "label_error"}
    result = {}
    for method, order in orders.items():
        if len(order) != len(ids) or set(order) != ids:
            raise ValueError("Ranking must cover every case exactly once")
        selected = set(order[:budget])
        hits = len(selected & positives)
        result[method] = {
            "precision_at_budget": hits / budget,
            "recall": hits / len(positives) if positives else None,
            "hits": hits,
            "budget": budget,
            "positive_images": len(positives),
        }
    return result


def verify_frozen(root):
    root = Path(root)
    receipt = read(root / "reports/human_v1/freeze.json")
    for name, expected in receipt["files"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen human benchmark drift: " + name)
    return read(root / "reports/human_v1/manifest.json")
