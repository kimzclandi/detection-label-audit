"""Validate real submissions, assemble third-review packet, gate final scoring."""

import argparse
import shutil
from pathlib import Path

from core import digest, evaluate, immutable, read, reconcile, verify_frozen

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["reconcile", "score"])
    p.add_argument("--a", type=Path, required=True)
    p.add_argument("--b", type=Path, required=True)
    p.add_argument("--c", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--packet-root", type=Path)
    args = p.parse_args()
    manifest = verify_frozen(ROOT)
    a, b = read(args.a), read(args.b)
    result = reconcile(manifest, a, b, read(args.c) if args.c else None)
    result["submission_hashes"] = {
        "A": digest(a),
        "B": digest(b),
        "C": digest(read(args.c)) if args.c else None,
    }
    if args.action == "score":
        orders = read(ROOT / "reports/human_v1/orders.json")
        if orders["protocol"] != digest(manifest):
            raise ValueError("Ranking protocol drift")
        result["scores"] = evaluate(manifest, result, orders["orders"], budget=8)
    immutable(args.output, result)
    if args.packet_root and args.action == "reconcile":
        pending = {r["case_id"]: r for r in result["pending"] if r["status"] == "needs_third_person"}
        if pending:
            directory = args.packet_root / "reviewer-C"
            if directory.exists():
                raise ValueError("Existing arbiter packet: use new output root to preserve history")
            (directory / "images").mkdir(parents=True)
            for cid in pending:
                shutil.copyfile(
                    args.packet_root / "reviewer-A/images" / f"{cid}.jpg", directory / "images" / f"{cid}.jpg"
                )
            import json

            payload = {
                "protocol": digest(manifest),
                "role": "C",
                "cases": [r for r in manifest["cases"] if r["case_id"] in pending],
                "classes": manifest["classes"],
                "prior_reviews": {cid: r["reviews"] for cid, r in pending.items()},
            }
            page = (
                (ROOT / "human_v1/review.html")
                .read_text()
                .replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c"))
            )
            (directory / "review.html").write_text(page)
            for name in ("REVIEW_GUIDE.md", "BDD100K_LICENSE.rst"):
                shutil.copyfile(args.packet_root / "reviewer-A" / name, directory / name)
    print({"status": result["status"], "gold_cases": len(result["gold"]), "pending": len(result["pending"])})


if __name__ == "__main__":
    main()
