"""Post-run statistical correction: rerank bootstrap copies under the exact review budget."""

from pathlib import Path

import numpy as np

from label_audit import immutable, read


def reranked_precision(order, truth, draw, budget):
    # Draw contains empirical image-group copies; rank each copy with its frozen order.
    priority = {sid: i for i, sid in enumerate(order)}
    selected = sorted(enumerate(draw), key=lambda pair: (priority[pair[1]], pair[0]))[:budget]
    if len(selected) != budget:
        raise ValueError("Bootstrap must preserve review budget")
    return sum(sid in truth for _, sid in selected) / budget


def main():
    root = Path(__file__).resolve().parent
    r = read(root / "reports/result.json")
    ids = sorted(x["id"] for x in read(root / "reports/reference.json")["rows"] if x["split"] == "eval")
    seeds = [1301, 2309, 3301]
    truth = {s: read(root / f"reports/runs/s{s}.json")["truth"] for s in seeds}
    orders = {(x["seed"], x["method"]): x["review_order"] for x in r["records"] if x["budget_images"] == 12}
    rng = np.random.default_rng(911206)
    vals = []
    for _ in range(2000):
        draw = rng.choice(ids, size=len(ids), replace=True).tolist()
        vals.append(
            sum(
                reranked_precision(orders[s, "combined"], truth[s], draw, 12)
                - reranked_precision(orders[s, "geometry"], truth[s], draw, 12)
                for s in seeds
            )
            / len(seeds)
        )
    exact = sum(
        next(
            x["precision_at_budget"]
            for x in r["records"]
            if x["seed"] == s and x["method"] == "combined" and x["budget_images"] == 12
        )
        - next(
            x["precision_at_budget"]
            for x in r["records"]
            if x["seed"] == s and x["method"] == "geometry" and x["budget_images"] == 12
        )
        for s in seeds
    ) / len(seeds)
    out = {
        "primary_delta": exact,
        "reranked_group_bootstrap_ci95": np.quantile(vals, [0.025, 0.975]).tolist(),
        "draws": 2000,
        "seed": 911206,
        "budget_per_draw": 12,
        "original_interval_status": "REJECTED as precision@budget uncertainty: fixed selected-hit indicators resampled without reranking can violate fixed budget interpretation.",
        "scope": "Post-run statistical repair, not a new confirmatory experiment. Repeated empirical groups are bootstrap copies, each counted toward 12 reviews. Same group draw across methods/seeds. Conditional on original three contamination seeds and frozen rankings.",
        "decision": "No incremental combined-policy evidence; synthetic easy-error concentration prevents general quality claims.",
    }
    immutable(root / "reports/metric_audit.json", out)
    print(out)


if __name__ == "__main__":
    main()
