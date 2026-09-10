"""Freeze synthetic-label experiment before contamination, then preserve all evidence."""

import argparse
import time
from pathlib import Path

import numpy as np

from label_audit import audit, digest, file_hash, immutable, inject, metrics, observed, rank, read

ROOT = Path(__file__).resolve().parents[1]
SEEDS = [1301, 2309, 3301]
METHODS = ["random", "geometry", "combined"]


def identity():
    return {
        "reference": file_hash(ROOT / "reports/reference.json"),
        "code": {
            str(p.relative_to(ROOT)): file_hash(p) for p in [ROOT / "src/label_audit.py", Path(__file__)]
        },
        "lock": file_hash(ROOT / "uv.lock"),
    }


def freeze():
    immutable(
        ROOT / "reports/protocol.json",
        {
            "identity": identity(),
            "seeds": SEEDS,
            "methods": METHODS,
            "primary_budget_images": 12,
            "secondary_budget_images": 24,
            "primary": "mean paired precision@12 combined-minus-geometry over three fixed contamination seeds, then image-group bootstrap 2000 resamples (seed911206); no threshold/weight tuning",
            "pollution": "Five equally represented types, one inserted problem per polluted image; 50% images polluted, seed-controlled. Missing/class/half-size box/exact duplicate/normalized-coordinate pipeline.",
            "reference": "Unmodified public BDD labels, NOT independently adjudicated clean. Ground truth is synthetic injection delta only.",
            "splits": "36 previous dev images (not used for tuning);120 heldout source image groups for new synthetic corruption experiment. These images were evaluated for detection in another project, so not a new detector test set.",
            "review_unit": "Image review, not per-box or human time. One injected issue per polluted image. Per-type recall counts reviewed polluted images, not issue-type classification accuracy.",
            "scoring": "Geometry contract/exact duplicates=10 or20; plus MAX fixed detector disagreement>=.7. Auditor receives observed labels/predictions only; corruption truth never passed.",
            "decision": "No real-label-error performance claim without independent human adjudication. No automatic repair, no model retraining. Preserve negative result and all clean false alarms.",
            "statistical_unit": "image prefix group; contamination draws on shared source images are paired, not independent datasets",
            "stop": "Run all three seeds once; freeze all results, do not seek favorable corruption or budget.",
        },
    )


def run(verify=False, limit=None):
    p = read(ROOT / "reports/protocol.json")
    if p["identity"] != identity():
        raise ValueError("Frozen protocol/source drift")
    source = read(ROOT / "reports/reference.json")
    rows = [r for r in source["rows"] if r["split"] == "eval"]
    if len({r["group"] for r in rows}) != len(rows):
        raise ValueError("Expected unique evaluation groups")
    if {r["group"] for r in rows} & {r["group"] for r in source["rows"] if r["split"] == "dev"}:
        raise ValueError("Group leakage")
    results = []
    binary = {}
    costs = []
    for seed in SEEDS[:limit]:
        t = time.perf_counter()
        corrupted, truth, changes = inject(rows, seed)
        records = [audit(r) for r in corrupted]
        evidence = {
            "protocol": digest(p),
            "observed": corrupted,
            "truth": truth,
            "changes": changes,
            "candidates": records,
        }
        immutable(ROOT / f"reports/runs/s{seed}.json", evidence)
        orders = {method: rank(records, method, seed) for method in METHODS}
        for method in METHODS:
            for budget in (12, 24):
                results.append(
                    {
                        "seed": seed,
                        "method": method,
                        **metrics(orders[method], truth, budget),
                        "review_order": orders[method],
                    }
                )
        binary[seed] = {
            method: {r["id"]: int(r["id"] in truth and r["id"] in orders[method][:12]) for r in rows}
            for method in METHODS
        }
        costs.append(time.perf_counter() - t)
    if limit:
        return print({"completed_seeds": len(results) // 6, "stopped_before_remaining": True})
    # Paired image bootstrap with fixed-size review decisions: estimate paired selected-hit rates
    # scaled by N/budget. This is a conditional design statistic, not reranking bootstrap.
    ids = sorted(r["id"] for r in rows)
    deltas = np.asarray(
        [np.mean([binary[s]["combined"][i] - binary[s]["geometry"][i] for s in SEEDS]) for i in ids]
    )
    rng = np.random.default_rng(911206)
    boot = rng.choice(deltas, size=(2000, len(ids))).mean(axis=1) * len(ids) / 12
    result = {
        "records": results,
        "paired_precision_delta": float(deltas.sum() / 12),
        "ci95": np.quantile(boot, [0.025, 0.975]).tolist(),
        "interval_scope": "Conditional fixed review decisions, image resampling of paired hit indicators scaled by N/12; does not rerank or model all acquisition randomness.",
        "real_cases_status": "No independent human adjudication; all unmodified-source candidates pending_review",
    }
    original = [audit(observed(r)) for r in rows]
    pending = {
        "scope": "Original unmodified annotations, no injected truth. Rankings only, not measured real error precision.",
        "candidates": original,
        "review_order": rank(original, "combined", 1301),
        "status": "pending_review",
    }
    if verify:
        if result != read(ROOT / "reports/result.json") or pending != read(
            ROOT / "reports/real_pending.json"
        ):
            raise ValueError("Replay mismatch")
        print("Verified all three corruptions, 18 budget evaluations, raw candidates and pending real queue")
    else:
        immutable(ROOT / "reports/result.json", result)
        immutable(ROOT / "reports/real_pending.json", pending)
        if not (ROOT / "reports/cost.json").exists():
            immutable(
                ROOT / "reports/cost.json",
                {
                    "seed_seconds": costs,
                    "total_seconds": sum(costs),
                    "scope": "CPU annotation auditing using previously computed detector predictions; no neural inference or training included",
                },
            )
        print(
            {
                "paired_precision_delta": result["paired_precision_delta"],
                "ci95": result["ci95"],
                "cost_seconds": sum(costs),
            }
        )


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("action", choices=["freeze", "run", "verify"])
    a.add_argument("--limit", type=int)
    args = a.parse_args()
    if args.action == "freeze":
        freeze()
    else:
        run(args.action == "verify", args.limit)
