"""Freeze uniform human review sample; no model suggestions enter reviewer packets."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from core import digest, immutable, read

ROOT = Path(__file__).resolve().parents[1]


def main(images, output):
    reference = read(ROOT / "reports/reference.json")
    rows = [r for r in reference["rows"] if r["split"] == "eval"]
    if len({r["group"] for r in rows}) != 120:
        raise ValueError("Expected 120 unique source groups")
    chosen = sorted(rows, key=lambda r: digest(["human-v1-911207", r["id"]]))[:40]
    cases = []
    mapping = []
    for row in chosen:
        cid = "H-" + digest(["blind-human-v1", row["id"]])[:12]
        raw = (images / (row["id"] + ".jpg")).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["image_sha256"]:
            raise ValueError("Source image drift")
        cases.append(
            {
                "case_id": cid,
                "width": row["width"],
                "height": row["height"],
                "image_sha256": row["image_sha256"],
                "labels": row["labels"],
            }
        )
        mapping.append({"case_id": cid, "source_id": row["id"], "group": row["group"]})
    manifest = {
        "version": "human-v1",
        "seed": 911207,
        "sampling": "uniform deterministic hash sample 40 of 120 unique eval groups, no model/label-based selection",
        "source_reference_sha256": hashlib.sha256((ROOT / "reports/reference.json").read_bytes()).hexdigest(),
        "cases": cases,
        "primary_budget": 8,
        "scope": "40-image subset ranking benchmark; not full-pool precision or new detection generalization",
        "adjudication": "A/B independently inspect raw image and current labels. All positives, disagreements and unresolved cases require third person C. No scores before complete resolved adjudication.",
        "target": "Errors in seven-class derived annotation contract, not automatically errors in original BDD taxonomy",
        "classes": {
            "1": "person (includes rider)",
            "2": "bicycle",
            "3": "car",
            "4": "motorcycle",
            "6": "bus",
            "8": "truck",
            "10": "traffic light",
        },
        "label_rule": "Only clear visible objects in task scope. Ambiguous, very small, occluded or taxonomy-dependent cases unresolved. Regions in original pixel coordinates. Do not infer correctness from detector predictions.",
    }
    immutable(ROOT / "reports/human_v1/manifest.json", manifest)
    immutable(output / "coordinator/mapping.json", {"protocol": digest(manifest), "rows": mapping})
    source = {r["case_id"]: r["source_id"] for r in mapping}
    template = (ROOT / "human_v1/review.html").read_text()
    for role in ("A", "B"):
        directory = output / ("reviewer-" + role)
        (directory / "images").mkdir(parents=True, exist_ok=True)
        ordered = sorted(cases, key=lambda r: digest([role, r["case_id"]]))
        payload = {
            "protocol": digest(manifest),
            "role": role,
            "cases": ordered,
            "classes": manifest["classes"],
        }
        for case in cases:
            dest = directory / "images" / (case["case_id"] + ".jpg")
            raw = (images / (source[case["case_id"]] + ".jpg")).read_bytes()
            if dest.exists() and dest.read_bytes() != raw:
                raise ValueError("Packet image drift")
            dest.write_bytes(raw)
        page = template.replace(
            "__PAYLOAD__", json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
        )
        dest = directory / "review.html"
        if dest.exists() and dest.read_text() != page:
            raise ValueError("Review UI changed; new version required")
        dest.write_text(page)
        shutil.copyfile(ROOT / "docs/BDD100K_LICENSE.rst", directory / "BDD100K_LICENSE.rst")
        shutil.copyfile(ROOT / "human_v1/REVIEW_GUIDE.md", directory / "REVIEW_GUIDE.md")
    immutable(
        output / "STATUS.json",
        {
            "status": "awaiting_real_human_reviews",
            "completed_human_reviews": 0,
            "gold_cases": 0,
            "protocol": digest(manifest),
            "cases": 40,
        },
    )
    from label_audit import rank

    original = read(ROOT / "reports/real_pending.json")
    mapping_ids = {r["source_id"]: r["case_id"] for r in mapping}
    records = [r for r in original["candidates"] if r["id"] in mapping_ids]
    orders = {
        method: [mapping_ids[sid] for sid in rank(records, method, 1301)]
        for method in ("random", "geometry", "combined")
    }
    immutable(
        ROOT / "reports/human_v1/orders.json", {"protocol": digest(manifest), "seed": 1301, "orders": orders}
    )
    files = (
        [
            ROOT / "reports/human_v1/manifest.json",
            ROOT / "reports/human_v1/orders.json",
            ROOT / "reports/reference.json",
            ROOT / "reports/real_pending.json",
        ]
        + sorted((ROOT / "human_v1").glob("*.py"))
        + sorted((ROOT / "human_v1").glob("*.html"))
        + sorted((ROOT / "human_v1").glob("*.md"))
    )
    immutable(
        ROOT / "reports/human_v1/freeze.json",
        {
            "files": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            "status": "awaiting_humans",
            "gold_cases": 0,
        },
    )
    print(
        "Prepared 40 images x 2 blinded reviewer packets. No human judgments or benchmark scores generated."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.images, args.output)
