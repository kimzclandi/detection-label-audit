"""AI-assisted source-use ledger and gated real-label evaluation. Never invent reviews."""

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "human_v1"))
from core import evaluate, reconcile  # noqa: E402

from audit_diagnosis import guarded  # noqa: E402
from label_audit import audit, digest, file_hash, immutable, rank, read  # noqa: E402

OUT = ROOT / "reports/readiness_v3"
BOUND = [
    "src/label_audit.py",
    "src/audit_diagnosis.py",
    "human_v1/core.py",
    "scripts/readiness_v3.py",
    "uv.lock",
    "reports/reference.json",
    "reports/human_v1/manifest.json",
    "reports/diagnosis_v2/result.json",
]


def ledger(source, reference):
    ids = [r["sample_id"] for r in source]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate source ID")
    audit_groups = {r["group"] for r in reference}
    seed_groups = {r["group_id"] for r in source if r["split"] == "seed"}
    history = []
    for r in sorted(source, key=lambda r: r["sample_id"]):
        reasons = []
        if r["group_id"] in audit_groups:
            reasons.append("prior_label_audit_source_group")
        if r["group_id"] in seed_groups:
            reasons.append("warmup_training_source_group")
        if r["split"] != "test":
            reasons.append("not_preexisting_detector_test_partition")
        history.append(
            {
                "id": r["sample_id"],
                "group": r["group_id"],
                "upstream_split": r["split"],
                "image_sha256": r["sha256"],
                "canonical_labels_sha256": r["labels_sha256"],
                "excluded_reasons": reasons,
                "reserved": not reasons,
                "never_used_upstream": False,
            }
        )
    reserved = [r for r in history if r["reserved"]]
    if len({r["group"] for r in reserved}) != len(reserved):
        raise ValueError("Reserved pool must contain one image per source group")
    return {
        "rows": history,
        "reserved_ids": [r["id"] for r in reserved],
        "counts_by_split": dict(sorted(Counter(r["split"] for r in source).items())),
        "reserved_images": len(reserved),
        "reserved_groups": len({r["group"] for r in reserved}),
        "excluded_images": len(history) - len(reserved),
        "status": "RESERVED_UNSCORED_NO_REAL_GOLD",
        "real_error_metrics": None,
    }


def identity():
    return {p: file_hash(ROOT / p) for p in BOUND}


def prepare(upstream):
    source_path = upstream / "data/manifest.json"
    source = read(source_path)["rows"]
    ref = read(ROOT / "reports/reference.json")["rows"]
    result = ledger(source, ref)
    by_id = {r["sample_id"]: r for r in source}
    cases = []
    for sid in result["reserved_ids"]:
        r = by_id[sid]
        image = upstream / r["image_path"]
        labels = upstream / "data/labels" / (sid + ".json")
        if file_hash(image) != r["sha256"] or digest(read(labels)) != r["labels_sha256"]:
            raise ValueError("Source identity drift: " + sid)
        cases.append(
            {
                "case_id": "R3-" + digest(["reserve-v3", sid])[:12],
                "source_id": sid,
                "group": r["group_id"],
                "width": r["width"],
                "height": r["height"],
                "image_sha256": r["sha256"],
                "labels": read(labels),
            }
        )
    # Names are inspected, not unseen image content or audit scores.
    available = sorted(p.stem for p in (upstream / "data/images").glob("*.jpg"))
    known = set(by_id) | {r["id"] for r in ref}
    if set(available) - known:
        raise ValueError("Uncatalogued local sources require separate provenance audit")
    manifest = {
        "version": "reserve-v3",
        "cases": cases,
        "budget_images": 8,
        "methods": ["random", "geometry", "combined", "guarded"],
        "seed": 911301,
        "selection": "All existing upstream test-partition groups excluding any "
        "audit-development/evaluation or warmup-training groups. No score-based selection.",
        "status": "Reserved only; no new claims and no request for human work in this run",
        "history": "Previously used for upstream detector test; new only to this label-audit study.",
        "review_rule": "Two distinct independent human raw per-image submissions; "
        "all positives/disagreements/unresolved cases need third-person adjudication. "
        "No-error-found is not proof of error-free labels. Self-attestation is not identity verification.",
        "scope": "Seven derived classes. BDD reference is not adjudicated gold.",
        "model": read(ROOT / "reports/diagnosis_v2/provenance.json")["model_config"],
    }
    snapshot = {
        "upstream_manifest_rows": source,
        "local_image_ids": available,
        "upstream_manifest_sha256": file_hash(source_path),
        "upstream_prediction_sha256": file_hash(upstream / "reports/pilot/baseline/predictions.json"),
        "upstream_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=upstream, text=True
        ).strip(),
    }
    immutable(OUT / "source_snapshot.json", snapshot)
    immutable(OUT / "ledger.json", result)
    immutable(OUT / "manifest.json", manifest)
    immutable(
        OUT / "freeze.json",
        {
            "identity": identity(),
            "artifacts": {
                n: file_hash(OUT / n) for n in ["source_snapshot.json", "ledger.json", "manifest.json"]
            },
            "parent_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "rule": "No scores or new synthetic experiment. Future scoring must match this frozen identity. "
            "Changes require another version, never overwrite reserve-v3.",
        },
    )
    print({k: v for k, v in result.items() if k not in ["rows", "reserved_ids"]})


def verify():
    frozen = read(OUT / "freeze.json")
    if frozen["identity"] != identity():
        raise ValueError("Frozen code/model/reference identity drift")
    for name, sha in frozen["artifacts"].items():
        if file_hash(OUT / name) != sha:
            raise ValueError("Frozen reservation artifact drift")
    snapshot = read(OUT / "source_snapshot.json")
    ref = read(ROOT / "reports/reference.json")["rows"]
    expected = ledger(snapshot["upstream_manifest_rows"], ref)
    if expected != read(OUT / "ledger.json"):
        raise ValueError("Source ledger replay mismatch")
    manifest = read(OUT / "manifest.json")
    if [c["source_id"] for c in manifest["cases"]] != expected["reserved_ids"]:
        raise ValueError("Reserved case coverage mismatch")
    return manifest


def score_from_submissions(manifest, first, second, arbitration, orders):
    # Reuse the existing human contract; bulk/AI notes cannot substitute for raw submissions.
    if first is None or second is None:
        raise ValueError("Missing independent per-image A/B submissions; real-error scoring refused")
    adjudicated = reconcile(manifest, first, second, arbitration)
    scores = evaluate(manifest, adjudicated, orders, budget=manifest["budget_images"])
    return {
        "scope": "Against submitted adjudication only; negatives are no-error-found",
        "scores": scores,
        "adjudication": adjudicated,
        "submission_sha256": {
            k: digest(v) if v is not None else None
            for k, v in [("A", first), ("B", second), ("C", arbitration)]
        },
    }


def score(upstream, a, b, c, output):
    manifest = verify()
    first, second, arb = read(a), read(b), read(c) if c else None
    # Fail BEFORE computing scores/rankings if gold remains incomplete.
    adjudicated = reconcile(manifest, first, second, arb)
    if adjudicated["status"] != "ready":
        raise ValueError("Incomplete/unresolved raw reviews; no rankings or metrics generated")
    predfile = upstream / "reports/pilot/baseline/predictions.json"
    if file_hash(predfile) != read(OUT / "source_snapshot.json")["upstream_prediction_sha256"]:
        raise ValueError("Prediction cache identity drift")
    cache = {r["sample_id"]: r for r in read(predfile)["rows"]}
    old, new = [], []
    for case in manifest["cases"]:
        p = cache[case["source_id"]]
        if p["sha256"] != case["image_sha256"]:
            raise ValueError("Prediction image identity drift")
        row = {k: case[k] for k in ["width", "height", "labels", "group"]}
        row.update(id=case["case_id"], predictions=p["predictions"])
        old.append(audit(row))
        new.append(guarded(row))
    orders = {
        m: rank(new if m == "guarded" else old, "combined" if m == "guarded" else m, manifest["seed"])
        for m in manifest["methods"]
    }
    result = score_from_submissions(manifest, first, second, arb, orders)
    result["orders"] = orders
    immutable(output, result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "verify", "score"])
    parser.add_argument("--upstream", type=Path)
    parser.add_argument("--a", type=Path)
    parser.add_argument("--b", type=Path)
    parser.add_argument("--c", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        if args.upstream is None:
            parser.error("--upstream required")
        prepare(args.upstream)
    elif args.action == "verify":
        m = verify()
        print({"reserved_cases": len(m["cases"]), "scores_generated": False})
    else:
        if any(v is None for v in [args.upstream, args.a, args.b, args.output]):
            parser.error("--upstream, --a, --b and --output required; no fabricated reviews")
        score(args.upstream, args.a, args.b, args.c, args.output)
