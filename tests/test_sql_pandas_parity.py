from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.metrics import cohort_retention, create_sqlite_database, run_sql_file
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
    assert np.allclose(comparison["retention"], comparison["classical_retention"], atol=1e-6)
