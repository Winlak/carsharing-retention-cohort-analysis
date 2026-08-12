"""CLI wrapper for the reproducible synthetic data generator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.synthetic_data import (  # noqa: E402
    DEFAULT_DATA_END,
    GenerationConfig,
    write_synthetic_data,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic carsharing users and rides.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "generated")
    parser.add_argument("--n-users", type=int, default=6_000)
    parser.add_argument("--seed", type=int, default=20240801)
    parser.add_argument("--data-end", default=DEFAULT_DATA_END.isoformat())
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_end = pd.Timestamp(args.data_end)
    if data_end.tzinfo is None:
        data_end = data_end.tz_localize("UTC")
    else:
        data_end = data_end.tz_convert("UTC")
    users_path, rides_path = write_synthetic_data(
        args.output_dir,
        GenerationConfig(n_users=args.n_users, seed=args.seed, data_end=data_end),
    )
    print(f"Wrote {users_path}")
    print(f"Wrote {rides_path}")


if __name__ == "__main__":
    main()
