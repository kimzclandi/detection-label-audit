"""Build presentation numbers solely from immutable raw records."""

from diagnose_v2 import OUT, ROOT, save

from label_audit import read


def build():
    result = read(OUT / "result.json")
    corrected = read(OUT / "control_correction/result.json")["corrected_random_records"]
    records = [r for r in result["records"] if r["method"] != "random"] + corrected
    table = []
    for method in ["random", "geometry", "combined", "guarded"]:
        rows = [r for r in records if r["method"] == method]
        table.append(
            {
                "method": method,
                "hits_by_seed": [r["hits"] for r in rows],
                "mean_precision_at_8": sum(r["hits"] for r in rows) / 24,
                "by_type_hits": {
                    t: sum(r["by_type"][t]["hits"] for r in rows) for t in ["missing", "class", "box"]
                },
                "by_type_support_across_corruptions": 18,
                "unchanged_source_selections": sum(len(r["false_positive_ids"]) for r in rows),
            }
        )
    legacy = []
    for seed in [1301, 2309, 3301]:
        r = read(ROOT / f"reports/runs/s{seed}.json")
        from label_audit import rank

        g = rank(r["candidates"], "geometry", seed)
        c = rank(r["candidates"], "combined", seed)
        geometric = {x["id"] for x in r["candidates"] if x["geometry_score"] > 0}
        legacy.append(
            {
                "seed": seed,
                "geometry_images": len(geometric),
                "changed_positions": sum(a != b for a, b in zip(g, c, strict=True)),
                "top12_set_overlap": len(set(g[:12]) & set(c[:12])),
                "combined_top12_geometry": len(set(c[:12]) & geometric),
                "combined_top24_geometry": len(set(c[:24]) & geometric),
                "nongeometry_above_geometry": any(
                    c.index(n) < c.index(y) for n in set(c) - geometric for y in geometric
                ),
                "geometry_order": g,
                "combined_order": c,
            }
        )
    diagnostic = read(OUT / "development.json")
    masked = [
        dict(id=r["id"], **d)
        for r in diagnostic["records"]
        for d in r["deletions"]
        if d["new_missing"] and not d["score_rises"]
    ]
    missing = []
    for r in diagnostic["records"]:
        for e in r["original"]["evidence"]:
            if e["type"] == "missing_candidate":
                missing.append({"id": r["id"], **e})
    return {
        "table": table,
        "primary": {
            k: result[k] for k in ["mean_delta", "paired_deltas", "descriptive_percentile95", "source_groups"]
        },
        "legacy_ranking_audit_post_freeze_only": legacy,
        "new_missing_masked": masked,
        "original_missing_candidates": missing,
        "cpu_seconds": sum(read(p)["seconds"] for p in (OUT / "costs").glob("*.json")),
        "scope": "Exploratory dev-only synthetic error discovery. No real-error accuracy.",
        "decision": "KEEP_GUARD_FOR_EXPLORATORY_CANDIDATE_CLEANUP; REJECT_REAL_EFFECT_CLAIM",
    }


if __name__ == "__main__":
    import sys

    x = build()
    if "--verify" in sys.argv:
        if read(OUT / "presentation.json") != x:
            raise ValueError("Presentation replay drift")
    else:
        save(OUT / "presentation.json", x)
    print(x["table"])
    print("Masked", len(x["new_missing_masked"]), "CPU", x["cpu_seconds"])
    print(
        [{k: v for k, v in r.items() if "order" not in k} for r in x["legacy_ranking_audit_post_freeze_only"]]
    )
