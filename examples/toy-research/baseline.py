"""Deterministic TEST fixture for ResearchFlow's local-run pipeline."""

import argparse
import json
import os
from pathlib import Path

MULTIPLIER = 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=int, default=3)
    args = parser.parse_args()
    result = {"score": args.input * MULTIPLIER, "fixture": "TEST / MOCK"}
    run_dir = Path(os.environ["RF_RUN_DIR"])
    (run_dir / "metrics.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
