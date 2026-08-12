"""End-to-end reproducible pipeline for the portfolio case."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis import run_analysis  # noqa: E402
from src.metrics import assert_quality, create_sqlite_database, quality_profile  # noqa: E402
from src.report import build_markdown_report  # noqa: E402
from src.synthetic_data import (  # noqa: E402
    DEFAULT_DATA_END,
    GenerationConfig,
    write_synthetic_data,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate data, run SQL/pandas analysis, and render the case report."
    )
    parser.add_argument("--n-users", type=int, default=6_000)
    parser.add_argument("--seed", type=int, default=20240801)
    parser.add_argument("--data-end", default=DEFAULT_DATA_END.isoformat())
    return parser.parse_args()


def _parse_utc(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def main() -> None:
    args = parse_args()
    data_end = _parse_utc(args.data_end)
    generated_dir = ROOT / "data" / "generated"
    write_synthetic_data(generated_dir, GenerationConfig(args.n_users, args.seed, data_end))

    # Reload generated CSVs rather than passing in-memory objects: this makes
    # the extraction/load boundary explicit and catches serialization issues.
    users = pd.read_csv(generated_dir / "users.csv")
    rides = pd.read_csv(generated_dir / "rides.csv")
    users["registered_at"] = pd.to_datetime(users["registered_at"], utc=True, format="mixed")
    for column in ("attempted_at", "started_at", "completed_at"):
        rides[column] = pd.to_datetime(rides[column], utc=True, format="mixed")
    profile = quality_profile(users, rides, data_end)
    assert_quality(profile)
    database_path = generated_dir / "analysis.sqlite"
    create_sqlite_database(users, rides, database_path, data_end)
    outputs = run_analysis(
        users,
        rides,
        data_end=data_end,
        sql_dir=ROOT / "sql",
        database_path=database_path,
        figures_dir=ROOT / "figures",
        outputs_dir=ROOT / "outputs",
    )
    build_markdown_report(
        users=users,
        rides=rides,
        outputs=outputs,
        data_end=data_end,
        destination=ROOT / "reports" / "analytical_report.md",
    )
    print(f"Pipeline completed: {len(users):,} users, {len(rides):,} ride attempts")
    print(f"Report: {ROOT / 'reports' / 'analytical_report.md'}")


if __name__ == "__main__":
    main()
