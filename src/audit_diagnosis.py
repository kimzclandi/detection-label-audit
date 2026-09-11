"""AI-assisted development diagnostics; reference agreement is not human truth."""

import copy
import math
from collections import Counter

from label_audit import CLASSES, audit, iou, observed, rank


def validate(rows):
    ids = set()
    for r in rows:
        if r["id"] in ids:
            raise ValueError("Duplicate source id")
        ids.add(r["id"])
        if not all(math.isfinite(r[k]) and r[k] > 0 for k in ("width", "height")):
            raise ValueError("Invalid dimensions")
        for kind in ("labels", "predictions"):
            for x in r[kind]:
                b = x["box"]
                if len(b) != 4 or not all(math.isfinite(v) for v in b):
                    raise ValueError("Malformed box")
                if not 0 <= b[0] < b[2] <= r["width"] or not 0 <= b[1] < b[3] <= r["height"]:
                    raise ValueError("Invalid box contract")
                if x["label"] not in CLASSES:
                    raise ValueError("Invalid class")
                if kind == "predictions" and not (math.isfinite(x["score"]) and 0 <= x["score"] <= 1):
                    raise ValueError("Invalid confidence")


def explained_elsewhere(row, evidence):
    """Only suppress box-offset evidence; never silently drop class/missing evidence."""
    if evidence["type"] != "box_candidate":
        return False
    p = row["predictions"][evidence["prediction_index"]]
    return any(
        j != evidence["label_index"] and g["label"] == p["label"] and iou(g["box"], p["box"]) >= 0.5
        for j, g in enumerate(row["labels"])
    )


def guarded(row):
    result = audit(row)
    result["suppressed"] = [e for e in result["evidence"] if explained_elsewhere(row, e)]
    result["evidence"] = [e for e in result["evidence"] if not explained_elsewhere(row, e)]
    result["combined_score"] = result["geometry_score"] + max(
        (e["score"] for e in result["evidence"] if "score" in e), default=0
    )
    return result


def diagnose(row):
    original = observed(row)
    a, b = audit(original), guarded(original)
    high = [(k, p) for k, p in enumerate(row["predictions"]) if p["score"] >= 0.7]
    matches = []
    used = set()
    for k, p in sorted(high, key=lambda kp: (-kp[1]["score"], kp[0])):
        eligible = [
            (iou(p["box"], g["box"]), j)
            for j, g in enumerate(row["labels"])
            if j not in used and g["label"] == p["label"] and iou(p["box"], g["box"]) >= 0.5
        ]
        if eligible:
            overlap, j = max(eligible)
            used.add(j)
            matches.append({"prediction_index": k, "label_index": j, "iou": overlap})
    deletions = []
    old_missing = {e["prediction_index"] for e in a["evidence"] if e["type"] == "missing_candidate"}
    for j, lab in enumerate(row["labels"]):
        z = copy.deepcopy(original)
        z["labels"].pop(j)
        d = audit(z)
        newly = [
            e
            for e in d["evidence"]
            if e["type"] == "missing_candidate" and e["prediction_index"] not in old_missing
        ]
        deletions.append(
            {
                "label_index": j,
                "class": lab["label"],
                "new_missing": newly,
                "original_score": a["combined_score"],
                "deleted_score": d["combined_score"],
                "score_rises": d["combined_score"] > a["combined_score"],
            }
        )
    return {
        "id": row["id"],
        "group": row["group"],
        "original": a,
        "guarded": b,
        "reference_matches": matches,
        "deletions": deletions,
        "high_prediction_count": len(high),
        "multi_label_predictions": [
            k for k, p in high if sum(iou(p["box"], g["box"]) >= 0.5 for g in row["labels"]) > 1
        ],
    }


def summarize(rows, records):
    counts = Counter()
    coverage = {str(c): {"reference_objects": 0, "matched_objects": 0} for c in sorted(CLASSES)}
    for r, d in zip(rows, records, strict=True):
        a = d["original"]
        counts["images"] += 1
        counts["geometry_images"] += a["geometry_score"] > 0
        counts["model_images"] += a["combined_score"] > a["geometry_score"]
        counts["guarded_model_images"] += d["guarded"]["combined_score"] > a["geometry_score"]
        counts["box_candidates"] += sum(e["type"] == "box_candidate" for e in a["evidence"])
        counts["cross_box_candidates"] += len(d["guarded"]["suppressed"])
        ev = [e for e in a["evidence"] if "score" in e]
        win = [e for e in ev if e["score"] == max(x["score"] for x in ev)]
        counts["cross_max_images"] += bool(win) and all(explained_elsewhere(r, e) for e in win)
        counts["missing_candidates"] += sum(e["type"] == "missing_candidate" for e in ev)
        counts["high_predictions"] += d["high_prediction_count"]
        counts["multi_label_predictions"] += len(d["multi_label_predictions"])
        counts["deletions"] += len(d["deletions"])
        counts["deletion_new_missing"] += sum(bool(x["new_missing"]) for x in d["deletions"])
        counts["deletion_score_rises"] += sum(x["score_rises"] for x in d["deletions"])
        for g in r["labels"]:
            coverage[str(g["label"])]["reference_objects"] += 1
        for m in d["reference_matches"]:
            coverage[str(r["labels"][m["label_index"]]["label"])]["matched_objects"] += 1
    orders = {m: rank([r["original"] for r in records], m, 1301) for m in ("random", "geometry", "combined")}
    ranks = [
        {
            "id": r["id"],
            "geometry_rank": orders["geometry"].index(r["id"]) + 1,
            "combined_rank": orders["combined"].index(r["id"]) + 1,
        }
        for r in rows
    ]
    return {
        "counts": dict(counts),
        "coverage": coverage,
        "orders": orders,
        "ranks": ranks,
        "changed_ranks": sum(r["geometry_rank"] != r["combined_rank"] for r in ranks),
        "scope": "Development prediction behavior and synthetic deletion only. No real-label-error accuracy.",
    }
