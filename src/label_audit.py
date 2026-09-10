"""Review ranking using only observed labels and fixed predictions, never clean targets."""

import copy
import hashlib
import json
import math
import random
from pathlib import Path

TYPES = ["missing", "class", "box", "duplicate", "pipeline"]
CLASSES = {1, 2, 3, 4, 6, 8, 10}
FIELDS = {"id", "group", "width", "height", "labels", "predictions"}


def digest(x):
    return hashlib.sha256(
        json.dumps(x, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def read(p):
    return json.loads(Path(p).read_text())


def file_hash(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def immutable(p, x):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        if read(p) != x:
            raise ValueError("Immutable evidence mismatch")
    else:
        with p.open("x") as f:
            json.dump(x, f, indent=2, allow_nan=False)
            f.write("\n")


def observed(row):
    return {k: copy.deepcopy(row[k]) for k in FIELDS}


def inject(rows, seed):
    """Balanced single-error-per-image synthetic pollution, reference kept separate."""
    rng = random.Random(seed)
    eligible = sorted([r for r in rows if r["labels"]], key=lambda x: x["id"])
    per_type = len(rows) // 10
    chosen = rng.sample(eligible, per_type * len(TYPES))
    truth = {}
    changes = {}
    out = []
    for n, row in enumerate(chosen):
        typ = TYPES[n // per_type]
        truth[row["id"]] = typ
    for row in sorted(rows, key=lambda x: x["id"]):
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
            elif typ == "duplicate":
                r["labels"].append(copy.deepcopy(lab))
            elif typ == "pipeline":
                lab["box"] = [
                    v / (r["width"] if i % 2 == 0 else r["height"]) for i, v in enumerate(lab["box"])
                ]
            else:
                x1, y1, x2, y2 = lab["box"]
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                lab["box"] = [cx - (x2 - x1) / 4, cy - (y2 - y1) / 4, cx + (x2 - x1) / 4, cy + (y2 - y1) / 4]
            changes[r["id"]] = {
                "type": typ,
                "index": j,
                "before": old,
                "after_labels_sha256": digest(r["labels"]),
            }
        out.append(r)
    return out, truth, changes


def iou(a, b):
    overlap = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = max(0, a[2] - a[0]) * max(0, a[3] - a[1]) + max(0, b[2] - b[0]) * max(0, b[3] - b[1]) - overlap
    return overlap / union if union > 0 else 0.0


def audit(row):
    if set(row) != FIELDS:
        raise ValueError("Clean truth or unapproved fields in audit input")
    labels = row["labels"]
    preds = row["predictions"]
    evidence = []
    geometry = 0.0
    model = 0.0
    for j, lab in enumerate(labels):
        b = lab["box"]
        invalid = len(b) != 4 or not all(math.isfinite(v) for v in b)
        if not invalid:
            invalid = (
                b[2] <= b[0]
                or b[3] <= b[1]
                or b[0] < 0
                or b[1] < 0
                or b[2] > row["width"]
                or b[3] > row["height"]
                or lab["label"] not in CLASSES
            )
        if invalid:
            geometry = max(geometry, 20.0)
            evidence.append(
                {
                    "type": "pipeline_candidate",
                    "label_index": j,
                    "reason": "invalid coordinate or class contract",
                }
            )
            continue
        if max(b) <= 1.0 and row["width"] > 10:
            geometry = max(geometry, 10.0)
            evidence.append(
                {
                    "type": "pipeline_candidate",
                    "label_index": j,
                    "reason": "box looks normalized in a pixel-coordinate contract",
                }
            )
        if any(other["label"] == lab["label"] and other["box"] == b for other in labels[:j]):
            geometry = max(geometry, 10.0)
            evidence.append(
                {"type": "duplicate_candidate", "label_index": j, "reason": "exact same class and box"}
            )
        for k, p in enumerate(preds):
            if p["score"] < 0.7:
                continue
            overlap = iou(b, p["box"])
            if overlap >= 0.5 and p["label"] != lab["label"]:
                model = max(model, p["score"])
                evidence.append(
                    {
                        "type": "class_candidate",
                        "label_index": j,
                        "prediction_index": k,
                        "score": p["score"],
                        "iou": overlap,
                    }
                )
            elif 0.05 < overlap < 0.5 and p["label"] == lab["label"]:
                score = p["score"] * (1 - overlap)
                model = max(model, score)
                evidence.append(
                    {
                        "type": "box_candidate",
                        "label_index": j,
                        "prediction_index": k,
                        "score": score,
                        "iou": overlap,
                    }
                )
    for k, p in enumerate(preds):
        if p["score"] >= 0.7 and max((iou(p["box"], g["box"]) for g in labels), default=0) < 0.1:
            model = max(model, p["score"])
            evidence.append(
                {
                    "type": "missing_candidate",
                    "prediction_index": k,
                    "score": p["score"],
                    "reason": "high confidence detector box lacks nearby annotation; model FP remains possible",
                }
            )
    return {
        "id": row["id"],
        "group": row["group"],
        "geometry_score": geometry,
        "combined_score": geometry + model,
        "evidence": evidence,
        "status": "pending_review",
    }


def rank(records, method, seed):
    if method == "random":
        ids = sorted(r["id"] for r in records)
        random.Random(seed).shuffle(ids)
        return ids
    if method not in ("geometry", "combined"):
        raise ValueError("Unknown ranking")
    # Hash tie breaker independent of labels and truth; no floating equality policy tuning.
    return [r["id"] for r in sorted(records, key=lambda r: (-r[method + "_score"], digest([seed, r["id"]])))]


def metrics(order, truth, budget):
    if len(order) != len(set(order)) or not 0 < budget <= len(order):
        raise ValueError("Review budget or duplicate IDs")
    chosen = order[:budget]
    hits = [s for s in chosen if s in truth]
    return {
        "precision_at_budget": len(hits) / budget,
        "recall": len(hits) / len(truth) if truth else None,
        "hits": len(hits),
        "budget_images": budget,
        "corrupt_images": len(truth),
        "by_type": {
            t: {
                "hits": sum(truth.get(s) == t for s in chosen),
                "support": sum(v == t for v in truth.values()),
                "recall": sum(truth.get(s) == t for s in chosen) / sum(v == t for v in truth.values())
                if t in truth.values()
                else None,
            }
            for t in TYPES
        },
        "false_positive_ids": [s for s in chosen if s not in truth],
    }
