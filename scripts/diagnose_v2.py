"""Replayable dev diagnostics, frozen exploratory experiment, atomic resumable records."""

import argparse
import copy
import json
import os
import random
import subprocess
import time
from pathlib import Path

from audit_diagnosis import diagnose, guarded, summarize, validate
from label_audit import audit, digest, file_hash, metrics, observed, rank, read

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/diagnosis_v2"
METHODS = ["random", "geometry", "combined", "guarded"]
SEEDS = [911211, 911213, 911219]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if read(path) != value:
            raise ValueError("Evidence identity/content drift: " + str(path))
        return
    temp = path.with_suffix(".partial")
    with temp.open("w") as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def identity():
    paths = [
        "src/label_audit.py",
        "src/audit_diagnosis.py",
        "scripts/diagnose_v2.py",
        "reports/reference.json",
        "uv.lock",
        "reports/diagnosis_v2/provenance.json",
    ]
    return {p: file_hash(ROOT / p) for p in paths}


def development():
    rows = [r for r in read(ROOT / "reports/reference.json")["rows"] if r["split"] == "dev"]
    validate(rows)
    if len(rows) != 36:
        raise ValueError("Missing development images")
    return sorted(rows, key=lambda r: r["id"])


def diagnosis(verify=False):
    rows = development()
    records = [diagnose(r) for r in rows]
    payload = {
        "reference_hash": file_hash(ROOT / "reports/reference.json"),
        "records": records,
        "summary": summarize(rows, records),
    }
    if verify:
        if payload != read(OUT / "development.json"):
            raise ValueError("Diagnostic replay mismatch")
    else:
        save(OUT / "development.json", payload)
    print(json.dumps(payload["summary"]["counts"]))


def freeze():
    rows = development()
    t = time.perf_counter()
    for r in rows[:6]:
        guarded(observed(r))
    save(
        OUT / "pilot.json",
        {
            "images": [r["id"] for r in rows[:6]],
            "seconds": time.perf_counter() - t,
            "scope": "CPU guard only; no inference/training",
        },
    )
    save(
        OUT / "protocol.json",
        {
            "identity": identity(),
            "parent_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "hypothesis": "Suppress offset evidence from predictions already matching another same-class label. "
            "This reduces cross-object alarms without losing synthetic top-8 discovery.",
            "alternatives": [
                "Low detector coverage dominates",
                "MAX saturated by remaining evidence",
                "Suppression hides true offsets in crowded scenes",
            ],
            "status": "EXPLORATORY: all 36 dev images / 35 source groups already inspected; no independent confirmatory data",
            "data_version": "dev-three-error-v2",
            "diagnosis_hash": file_hash(OUT / "development.json"),
            "groups": [{"id": r["id"], "group": r["group"], "sha256": digest(r)} for r in rows],
            "excluded": "All 120 old eval groups including 40 human-feedback groups; no tuning on these",
            "methods": METHODS,
            "seeds": SEEDS,
            "budget_images": 8,
            "pollution": "18/36 images selected uniformly; 6 missing, 6 class, 6 half-width/height box. "
            "One random reference object per image. Same observed data for all methods.",
            "controls": "Same cached predictions, labels, geometry weights, score .7 and IoU .05/.1/.5. "
            "Guard affects only box_candidate explained by another same-class IoU>=.5 label.",
            "primary": "Mean paired precision@8 guarded minus combined across three seeds",
            "secondary": "Per-type reviewed-image recall; unchanged-source false alarms; full rankings and costs",
            "statistics": "Paired source-group reranking bootstrap, 2000 draws seed911223; all seeds share draws. "
            "Descriptive exploratory interval, not confirmation or equivalence.",
            "decision": "Retain guard as candidate cleanup only if primary >=0; reject ranking-improvement claim "
            "unless positive across every seed. Never claim real accuracy or training benefit.",
            "stop": "Exactly three seeds once. No tuning, new thresholds, additional methods, or favorable seeds. "
            "On missing/invalid input stop and retain failure; never drop denominator.",
            "cost_limit": "Local CPU cached audit only; stop above 60 seconds per seed; no paid services",
        },
    )


def corrupt(rows, seed):
    rng = random.Random(seed)
    eligible = [r for r in rows if r["labels"]]
    selected = rng.sample(eligible, 18)
    truth = {r["id"]: ["missing", "class", "box"][n // 6] for n, r in enumerate(selected)}
    result, changes = [], {}
    for row in rows:
        r = observed(row)
        typ = truth.get(r["id"])
        if typ:
            j = rng.randrange(len(r["labels"]))
            old = copy.deepcopy(r["labels"][j])
            lab = r["labels"][j]
            if typ == "missing":
                r["labels"].pop(j)
            elif typ == "class":
                lab["label"] = 1 if lab["label"] != 1 else 3
            else:
                x1, y1, x2, y2 = lab["box"]
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                lab["box"] = [cx - (x2 - x1) / 4, cy - (y2 - y1) / 4, cx + (x2 - x1) / 4, cy + (y2 - y1) / 4]
            changes[r["id"]] = {
                "type": typ,
                "label_index": j,
                "before": old,
                "after_labels_hash": digest(r["labels"]),
            }
        result.append(r)
    return result, truth, changes


def run(out=OUT, limit=None, verify=False):
    p = read(out / "protocol.json")
    if p["identity"] != identity():
        raise ValueError("Frozen identity drift")
    rows = development()
    if p["groups"] != [{"id": r["id"], "group": r["group"], "sha256": digest(r)} for r in rows]:
        raise ValueError("Frozen source group drift")
    all_results = []
    for seed in p["seeds"][:limit]:
        start = time.perf_counter()
        obs, truth, changes = corrupt(rows, seed)
        old, new = [audit(r) for r in obs], [guarded(r) for r in obs]
        orders = {
            m: rank(new if m == "guarded" else old, "combined" if m == "guarded" else m, seed)
            for m in METHODS
        }
        result = {
            "protocol_hash": digest(p),
            "observed": obs,
            "truth": truth,
            "changes": changes,
            "old_candidates": old,
            "guarded_candidates": new,
            "orders": orders,
            "metrics": {m: metrics(o, truth, 8) for m, o in orders.items()},
        }
        path = out / "runs" / f"s{seed}.json"
        if verify:
            if read(path) != result:
                raise ValueError("Run replay mismatch")
        else:
            save(path, result)
            elapsed = time.perf_counter() - start
            costpath = out / "costs" / f"s{seed}.json"
            if not costpath.exists():
                save(
                    costpath,
                    {"seconds": elapsed, "scope": "CPU all four methods plus evidence serialization"},
                )
            if elapsed > 60:
                raise TimeoutError("Frozen per-seed cost cap exceeded")
        all_results.append(result)
    if limit:
        return
    rng = random.Random(911223)
    groups = sorted({r["group"] for r in rows})
    by_group = {g: [r["id"] for r in rows if r["group"] == g] for g in groups}
    boot = []
    for _ in range(2000):
        sampled = [sid for g in rng.choices(groups, k=len(groups)) for sid in by_group[g]]
        diffs = []
        for r in all_results:
            scores = {}
            for m in ("guarded", "combined"):
                order = {sid: i for i, sid in enumerate(r["orders"][m])}
                picked = sorted(sampled, key=lambda sid: order[sid])[:8]
                scores[m] = sum(sid in r["truth"] for sid in picked) / 8
            diffs.append(scores["guarded"] - scores["combined"])
        boot.append(sum(diffs) / len(diffs))
    boot.sort()
    results = [
        {"seed": s, "method": m, **r["metrics"][m]}
        for s, r in zip(SEEDS, all_results, strict=True)
        for m in METHODS
    ]
    deltas = [
        r["metrics"]["guarded"]["precision_at_budget"] - r["metrics"]["combined"]["precision_at_budget"]
        for r in all_results
    ]
    summary = {
        "records": results,
        "paired_deltas": deltas,
        "mean_delta": sum(deltas) / 3,
        "descriptive_percentile95": [boot[49], boot[1949]],
        "source_groups": len(groups),
        "injection_seeds_not_independent": 3,
        "expected_runs": 3,
        "completed_runs": len(all_results),
        "failed_images": [],
        "real_label_error_accuracy": None,
    }
    if verify:
        if read(out / "result.json") != summary:
            raise ValueError("Summary replay mismatch")
    else:
        save(out / "result.json", summary)
    print(json.dumps({"mean_delta": summary["mean_delta"], "paired_deltas": deltas}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["diagnose", "freeze", "run", "verify"])
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    try:
        if args.action == "diagnose":
            diagnosis()
        elif args.action == "freeze":
            freeze()
        elif args.action == "verify":
            diagnosis(True)
            run(verify=True)
        else:
            run(limit=args.limit)
    except Exception as exc:
        if args.action != "verify":
            save(
                OUT / "failures" / f"{time.time_ns()}.json",
                {
                    "action": args.action,
                    "error": type(exc).__name__,
                    "message": str(exc),
                    "denominator_unchanged": True,
                },
            )
        raise
