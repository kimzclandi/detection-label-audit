"""Preserve invalid coupled random control; freeze and replay domain-separated replacement."""

import argparse
import random
import subprocess
from pathlib import Path

from diagnose_v2 import OUT, ROOT, save

from label_audit import digest, file_hash, metrics, read

DEST = OUT / "control_correction"


def identity():
    paths = [
        Path(__file__),
        ROOT / "scripts/diagnose_v2.py",
        ROOT / "src/label_audit.py",
        OUT / "result.json",
        OUT / "protocol.json",
        *sorted((OUT / "runs").glob("*.json")),
    ]
    return {str(p.relative_to(ROOT)): file_hash(p) for p in paths}


def independent_order(ids, seed):
    order = sorted(ids)
    random.Random(digest(["independent-review-order-v2", seed])).shuffle(order)
    return order


def main(action):
    if action == "freeze":
        save(
            DEST / "protocol.json",
            {
                "identity": identity(),
                "parent_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "reason": "Original random control shares RNG seed with pollution selection and is invalid. "
                "Original three random P@8 values are zero; retain as failed control.",
                "change": "Replace ONLY random review order using SHA256 domain independent-review-order-v2. "
                "Same images, truth, seeds, budget, all nonrandom scores/orders unchanged.",
                "stop": "One correction for all three seeds; no search; original primary paired delta unchanged.",
                "status": "Post-result protocol correction; exploratory, not a pristine confirmatory experiment",
            },
        )
        return
    p = read(DEST / "protocol.json")
    if p["identity"] != identity():
        raise ValueError("Control correction identity drift")
    records = []
    for path in sorted((OUT / "runs").glob("s*.json")):
        seed = int(path.stem[1:])
        r = read(path)
        order = independent_order([x["id"] for x in r["observed"]], seed)
        records.append({"seed": seed, "method": "random", "order": order, **metrics(order, r["truth"], 8)})
    result = {
        "protocol_hash": digest(p),
        "corrected_random_records": records,
        "nonrandom_results_sha256": file_hash(OUT / "result.json"),
        "invalid_original_random_retained": True,
    }
    if action == "verify":
        if read(DEST / "result.json") != result:
            raise ValueError("Corrected random replay mismatch")
    else:
        save(DEST / "result.json", result)
    print([(r["seed"], r["hits"]) for r in records])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["freeze", "run", "verify"])
    main(parser.parse_args().action)
