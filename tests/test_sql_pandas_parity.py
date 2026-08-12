from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.metrics import cohort_retention, create_sqlite_database, milestone_retention, run_sql_file
from src.synthetic_data import GenerationConfig, generate_synthetic_data


def test_sql_and_pandas_classical_retention_match(tmp_path: Path) -> None:
    config = GenerationConfig(n_users=550, seed=811)
    users, rides = generate_synthetic_data(config)
    database_path = tmp_path / "analysis.sqlite"
    create_sqlite_database(users, rides, database_path, config.data_end)
    sql_result = run_sql_file(database_path, Path("sql/cohort_retention.sql"))
    sql_result["cohort_week"] = pd.to_datetime(sql_result["cohort_week"])
    pandas_result = cohort_retention(rides, config.data_end, max_age=60, rolling=False)
    comparison = pandas_result.merge(
        sql_result, on=["cohort_week", "cohort_age"], suffixes=("_pd", "_sql")
    )
    assert len(comparison) == len(pandas_result)
    assert np.array_equal(
        comparison["eligible_users_pd"].to_numpy(dtype=int),
        comparison["eligible_users_sql"].to_numpy(dtype=int),
    )
    assert np.array_equal(
        comparison["retained_users_pd"].to_numpy(dtype=int),
        comparison["retained_users_sql"].to_numpy(dtype=int),
    )
    assert np.allclose(comparison["retention"], comparison["classical_retention"], atol=1e-6)

    rolling_result = cohort_retention(rides, config.data_end, max_age=60, rolling=True)
    pandas_milestones = milestone_retention(pandas_result, rolling_result)
    sql_milestones = run_sql_file(database_path, Path("sql/retention_milestones.sql"))
    sql_milestones["cohort_week"] = pd.to_datetime(sql_milestones["cohort_week"])
    milestone_comparison = pandas_milestones.merge(
        sql_milestones, on="cohort_week", suffixes=("_pd", "_sql")
    )
    assert len(milestone_comparison) == len(pandas_milestones)
    for column in ("eligible_d1", "eligible_d7", "eligible_d30"):
        assert np.array_equal(
            milestone_comparison[f"{column}_pd"].fillna(0).to_numpy(dtype=int),
            milestone_comparison[f"{column}_sql"].fillna(0).to_numpy(dtype=int),
        )
    for column in (
        "classic_d1",
        "classic_d7",
        "classic_d30",
        "rolling_d1",
        "rolling_d7",
        "rolling_d30",
    ):
        assert np.allclose(
            milestone_comparison[f"{column}_pd"],
            milestone_comparison[f"{column}_sql"],
            atol=1e-6,
            equal_nan=True,
        )
