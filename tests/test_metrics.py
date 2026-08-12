from __future__ import annotations

from pathlib import Path

import pandas as pd
import pandas.testing as pdt

from src.metrics import cohort_retention, early_outcomes, quality_profile
from src.synthetic_data import GenerationConfig, generate_synthetic_data


def _toy_rides() -> pd.DataFrame:
    rows = [
        ("R1", "U1", "2024-01-01 09:00:00+00:00"),
        ("R2", "U1", "2024-01-02 09:00:00+00:00"),
        ("R3", "U1", "2024-01-31 09:00:00+00:00"),
        ("R4", "U2", "2024-01-01 10:00:00+00:00"),
        ("R5", "U2", "2024-01-03 10:00:00+00:00"),
        ("R6", "U3", "2024-01-15 10:00:00+00:00"),
        ("R7", "U3", "2024-01-16 10:00:00+00:00"),
    ]
    frame = pd.DataFrame(rows, columns=["ride_id", "user_id", "completed_at"])
    frame["attempted_at"] = pd.to_datetime(frame["completed_at"], utc=True) - pd.Timedelta(
        minutes=3
    )
    frame["completed_at"] = pd.to_datetime(frame["completed_at"], utc=True)
    frame["status"] = "completed"
    return frame


def test_generator_is_deterministic_and_has_clean_hard_checks() -> None:
    config = GenerationConfig(n_users=500, seed=17)
    users_one, rides_one = generate_synthetic_data(config)
    users_two, rides_two = generate_synthetic_data(config)
    pdt.assert_frame_equal(users_one, users_two)
    pdt.assert_frame_equal(rides_one, rides_two)
    profile = quality_profile(users_one, rides_one, config.data_end)
    assert profile["result"].eq("pass").all()
    assert {"completed", "cancelled", "error"}.issuperset(rides_one["status"].unique())
    assert rides_one["status"].eq("completed").any()


def test_classical_and_rolling_use_different_numerators_and_eligible_denominator() -> None:
    rides = _toy_rides()
    end = pd.Timestamp("2024-01-31 23:59:59+00:00")
    classic = cohort_retention(rides, end, max_age=30, rolling=False)
    rolling = cohort_retention(rides, end, max_age=30, rolling=True)
    week = pd.Timestamp("2024-01-01")

    d1_classic = classic.loc[(classic["cohort_week"] == week) & (classic["cohort_age"] == 1)].iloc[
        0
    ]
    d1_rolling = rolling.loc[(rolling["cohort_week"] == week) & (rolling["cohort_age"] == 1)].iloc[
        0
    ]
    d30_classic = classic.loc[
        (classic["cohort_week"] == week) & (classic["cohort_age"] == 30)
    ].iloc[0]
    d30_rolling = rolling.loc[
        (rolling["cohort_week"] == week) & (rolling["cohort_age"] == 30)
    ].iloc[0]

    # U1 has D1 and D30; U2 only has D2; U3 is too young for D30.
    assert (d1_classic["eligible_users"], d1_classic["retained_users"]) == (2, 1)
    assert (d1_rolling["eligible_users"], d1_rolling["retained_users"]) == (2, 2)
    assert (d30_classic["eligible_users"], d30_classic["retained_users"]) == (2, 1)
    assert (d30_rolling["eligible_users"], d30_rolling["retained_users"]) == (2, 1)


def test_early_week_feature_excludes_day_30_to_prevent_leakage() -> None:
    rides = pd.DataFrame(
        [
            ("R1", "U1", "completed", "2024-01-01 08:00:00+00:00"),
            ("R2", "U1", "completed", "2024-01-31 08:00:00+00:00"),
            ("R3", "U2", "completed", "2024-01-01 08:00:00+00:00"),
            ("R4", "U2", "completed", "2024-01-08 08:00:00+00:00"),
        ],
        columns=["ride_id", "user_id", "status", "completed_at"],
    )
    rides["completed_at"] = pd.to_datetime(rides["completed_at"], utc=True)
    rides["attempted_at"] = rides["completed_at"] - pd.Timedelta(minutes=5)
    users = pd.DataFrame(
        {
            "user_id": ["U1", "U2"],
            "acquisition_channel": ["organic", "organic"],
            "city": ["Moscow", "Moscow"],
        }
    )
    outcomes = early_outcomes(rides, users, pd.Timestamp("2024-02-01 23:59:59+00:00"))
    u1 = outcomes.loc[outcomes["user_id"].eq("U1")].iloc[0]
    u2 = outcomes.loc[outcomes["user_id"].eq("U2")].iloc[0]
    assert (u1["rides_days_1_to_7"], u1["retained_d30_classic"]) == (0, 1)
    assert (u2["rides_days_1_to_7"], u2["retained_d30_classic"]) == (1, 0)


def test_sql_files_have_required_reusable_analytical_patterns() -> None:
    root = Path(__file__).resolve().parents[1]
    cohort_sql = (root / "sql" / "cohort_retention.sql").read_text(encoding="utf-8").upper()
    gap_sql = (root / "sql" / "ride_frequency_and_gaps.sql").read_text(encoding="utf-8").upper()
    assert "WITH RECURSIVE" in cohort_sql
    assert "LEFT JOIN" in cohort_sql
    assert "CROSS JOIN" in cohort_sql
    assert "ROW_NUMBER() OVER" in gap_sql
    assert "LAG(" in gap_sql
