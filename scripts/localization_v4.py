"""AI-assisted post-hoc localization audit; no new scorer, data, or rankings."""

import argparse
from pathlib import Path

from diagnose_v2 import save

from audit_diagnosis import guarded
from label_audit import audit, file_hash, iou, observed, read

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/localization_v4"
V2 = ROOT / "reports/diagnosis_v2"


def identity():
    paths = [
        Path(__file__),
        ROOT / "src/label_audit.py",
        ROOT / "src/audit_diagnosis.py",
        ROOT / "scripts/diagnose_v2.py",
        ROOT / "reports/reference.json",
        *sorted((V2 / "runs").glob("s*.json")),
    ]
    return {str(p.relative_to(ROOT)): file_hash(p) for p in paths}


def attribution(row, clean, change, candidate, baseline):
    """Truth is used only by this evaluator, never the ranking algorithm."""
    typ, index, target = change["type"], change["label_index"], change["before"]
    expected = {"missing": "missing_candidate", "class": "class_candidate", "box": "box_candidate"}[typ]
    matches = []
    for n, e in enumerate(candidate["evidence"]):
        if e["type"] != expected:
            continue
        if typ != "missing" and e.get("label_index") != index:
            continue
        p = row["predictions"][e["prediction_index"]]
        if p["label"] != target["label"] or iou(p["box"], target["box"]) < 0.5:
            continue
        # Same target-related evidence must disappear when the injected change is undone.
        if any(
            old["type"] == e["type"]
            and old.get("prediction_index") == e["prediction_index"]
            and (typ == "missing" or old.get("label_index") == e.get("label_index"))
            for old in baseline["evidence"]
        ):
            continue
        matches.append(n)
    scored = [(n, e["score"]) for n, e in enumerate(candidate["evidence"]) if "score" in e]
    peak = max((score for _, score in scored), default=0)
    winners = [n for n, score in scored if score == peak]
    return {
        "localized": bool(matches),
        "localized_evidence_indices": matches,
        "localized_at_max": bool(set(matches) & set(winners)),
        "all_max_evidence_localized": bool(winners) and set(winners) <= set(matches),
        "score_rises_after_injection": candidate["combined_score"] > baseline["combined_score"],
        "original_score": baseline["combined_score"],
        "injected_score": candidate["combined_score"],
    }


def build():
    frozen = read(OUT / "protocol.json")
    if frozen["identity"] != identity():
        raise ValueError("Frozen localization identity drift")
    reference = {r["id"]: r for r in read(ROOT / "reports/reference.json")["rows"] if r["split"] == "dev"}
    records = []
    for path in sorted((V2 / "runs").glob("s*.json")):
        run = read(path)
        seed = int(path.stem[1:])
        old = {r["id"]: r for r in run["old_candidates"]}
        new = {r["id"]: r for r in run["guarded_candidates"]}
        if {r["id"] for r in run["observed"]} != set(reference):
            raise ValueError("Missing/extra source images")
        for row in run["observed"]:
            sid = row["id"]
            clean = observed(reference[sid])
            change = run["changes"].get(sid)
            for method, fn, cache in [("combined", audit, old), ("guarded", guarded, new)]:
                candidate = fn(row)
                if candidate != cache[sid]:
                    raise ValueError("Candidate replay drift")
                base = fn(clean)
                if change and change["before"] != clean["labels"][change["label_index"]]:
                    raise ValueError("Injection target mismatch")
                trace = (
                    attribution(row, clean, change, candidate, base)
                    if change
                    else {
                        "localized": False,
                        "localized_evidence_indices": [],
                        "localized_at_max": False,
                        "all_max_evidence_localized": False,
                        "score_rises_after_injection": False,
                        "original_score": base["combined_score"],
                        "injected_score": candidate["combined_score"],
                    }
                )
                records.append(
                    {
                        "seed": seed,
                        "id": sid,
                        "group": row["group"],
                        "method": method,
                        "selected": sid in run["orders"][method][:8],
                        "type": run["truth"].get(sid),
                        **trace,
                    }
                )
    summaries = []
    for method in ["combined", "guarded"]:
        for typ in [None, "missing", "class", "box"]:
            rows = [r for r in records if r["method"] == method and (typ is None or r["type"] == typ)]
            positive = [r for r in rows if r["type"] is not None]
            chosen = [r for r in positive if r["selected"]]
            localized = [r for r in chosen if r["localized"]]
            summaries.append(
                {
                    "method": method,
                    "slice": typ or "all",
                    "review_budget_across_seeds": 24,
                    "injected_image_occurrences": len(positive),
                    "selected_injected_images": len(chosen),
                    "selected_localized_images": len(localized),
                    "selected_localized_at_max": sum(r["localized_at_max"] for r in chosen),
                    "selected_all_max_localized": sum(r["all_max_evidence_localized"] for r in chosen),
                    "selected_injected_without_localization": len(chosen) - len(localized),
                    "localized_selected_per_budget": len(localized) / 24,
                    "localized_any_rank": sum(r["localized"] for r in positive),
                    "localized_selected_per_selected_injected": len(localized) / len(chosen)
                    if chosen
                    else None,
                }
            )
    return {
        "summary": summaries,
        "records": records,
        "source_groups": 35,
        "scope": "Post-hoc attribution of frozen dev synthetic results; not real-error precision",
        "baseline_scope": "Random and geometry are ranking baselines, no localization metric assigned",
        "review_unit": "Image budget. Across-seed counts are repeated occurrences, not independent samples.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["freeze", "run", "verify"])
    action = parser.parse_args().action
    if action == "freeze":
        save(
            OUT / "protocol.json",
            {
                "identity": identity(),
                "status": "Post-hoc diagnostic; not confirmatory",
                "question": "Do selected injected images actually contain evidence localizing the injected target?",
                "definition": "Matching candidate type; same mutated label index for class/box; prediction same "
                "class as original target with original-box IoU>=0.5; candidate absent after undoing injection.",
                "max_definition": "Report any localized max and all-max-localized separately, preserving ties.",
                "boundaries": "IoU .5 is a declared heuristic attribution rule, not independent human truth. "
                "No score/threshold changes to auditor, no new corruption, no new rankings, no heldout59 access.",
                "stop": "Replay all three frozen seeds once, preserve all misses, no threshold sweep.",
            },
        )
    else:
        result = build()
        if action == "verify":
            if result != read(OUT / "result.json"):
                raise ValueError("Localization replay mismatch")
        else:
            save(OUT / "result.json", result)
        print(result["summary"])
