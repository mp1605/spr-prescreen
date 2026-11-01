"""Explicit, separately authorized evaluation command. Never called by the scanner."""

import argparse
from pathlib import Path

from backend.eval.runner import evaluate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorized-sponsor-evaluation", action="store_true", required=True)
    parser.add_argument("--papers", type=Path, required=True)
    parser.add_argument("--keys", type=Path, required=True)
    parser.add_argument("--crosswalk", type=Path, required=True)
    args = parser.parse_args()
    evaluate(Path(__file__).resolve().parents[1], args.papers, args.keys, args.crosswalk)


if __name__ == "__main__":
    main()
