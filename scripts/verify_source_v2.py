"""Optional local upstream validation; CI replays the vendored immutable reference instead."""

import argparse
from pathlib import Path

from label_audit import file_hash, read

ROOT = Path(__file__).resolve().parents[1]


def verify(upstream):
    ref = read(ROOT / "reports/reference.json")
    base = upstream / "reports/pilot/baseline/predictions.json"
    preds = {r["sample_id"]: r for r in read(base)["rows"]}
    checked = []
    for r in ref["rows"]:
        label_path = upstream / "data/labels" / (r["id"] + ".json")
        pred_path = (
            base
            if r["split"] == "dev"
            else upstream / "reports/failure_v2/runs/baseline/predictions" / (r["id"] + ".json")
        )
        pred = preds[r["id"]] if r["split"] == "dev" else read(pred_path)["prediction"]
        checks = [
            file_hash(label_path) == r["source_label_sha256"],
            read(label_path) == r["labels"],
            file_hash(pred_path) == r["source_prediction_sha256"],
            pred["predictions"] == r["predictions"],
            file_hash(upstream / "data/images" / (r["id"] + ".jpg")) == r["image_sha256"],
        ]
        if not all(checks):
            raise ValueError("Upstream source identity drift: " + r["id"])
        checked.append(r["id"])
    if file_hash(upstream / "models/warmup.pth") != ref["weights_sha256"]:
        raise ValueError("Checkpoint drift")
    print(f"Verified {len(checked)} reference images/labels/predictions and checkpoint")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", required=True, type=Path)
    verify(parser.parse_args().upstream)
