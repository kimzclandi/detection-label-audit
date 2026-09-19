"""Read-only saved-evidence verification using only the Python standard library."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    for name in ("localization_v4", "diagnose_v2", "correct_control_v2", "readiness_v3"):
        print(f"Checking {name}", flush=True)
        subprocess.run([sys.executable, str(ROOT / "scripts" / f"{name}.py"), "verify"],
                       cwd=ROOT, env=env, check=True)
    print("PASS: saved records verified; no model inference or real-label scoring performed.")


if __name__ == "__main__":
    main()
