"""Inspectable metric definitions used by the SQL and pandas analysis paths."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from src.synthetic_data import completed_rides, ensure_columns


def _day(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").dt.normalize().dt.tz_localize(None)


def build_cohorts(rides: pd.DataFrame) -> pd.DataFrame:
    """One row per activated user; cohort is the first *completed* ride day."""
    ensure_columns(rides, ["user_id", "status", "completed_at"], "rides")
    completed = completed_rides(rides)
    completed["ride_date"] = _day(completed["completed_at"])
    cohort = (
        completed.groupby("user_id", as_index=False)["ride_date"]
        .min()
        .rename(columns={"ride_date": "cohort_date"})
    )
    cohort["cohort_week"] = cohort["cohort_date"] - pd.to_timedelta(
        cohort["cohort_date"].dt.weekday, unit="D"
    )
    return cohort


def cohort_retention(
    rides: pd.DataFrame,
    data_end: pd.Timestamp,
    *,
    max_age: int = 60,
    rolling: bool = False,
) -> pd.DataFrame:
    """Calculate exact-day or rolling retention with age-specific eligibility.

    Classical retention counts a completed ride exactly at age N. Rolling
    retention counts a user if their final observed completed ride is at least
    age N. In both cases the denominator at N excludes cohorts not yet observed
    through N, preventing right-censoring from masquerading as churn.
    """
    data_end_day = pd.Timestamp(data_end).tz_convert("UTC").tz_localize(None).normalize()
    completed = completed_rides(rides)
    completed["ride_date"] = _day(completed["completed_at"])
    cohorts = build_cohorts(rides)
    activities = (
        completed[["user_id", "ride_date"]]
        .drop_duplicates()
        .merge(cohorts, on="user_id", how="inner")
    )
    activities["cohort_age"] = (activities["ride_date"] - activities["cohort_date"]).dt.days
    activities = activities.loc[activities["cohort_age"].between(0, max_age)]
    classic_numerator = (
        activities.groupby(["cohort_week", "cohort_age"], as_index=False)["user_id"]
        .nunique()
        .rename(columns={"user_id": "retained_users"})
    )
    last_active = (
        completed.groupby("user_id", as_index=False)["ride_date"]
        .max()
        .rename(columns={"ride_date": "last_ride_date"})
    )
    cohort_last = cohorts.merge(last_active, on="user_id", how="inner")

    rows: list[pd.DataFrame] = []
    for age in range(max_age + 1):
        base = cohort_last.loc[
            cohort_last["cohort_date"] + pd.Timedelta(days=age) <= data_end_day
        ].copy()
        denominator = (
            base.groupby("cohort_week", as_index=False)["user_id"]
            .nunique()
            .rename(columns={"user_id": "eligible_users"})
        )
        denominator["cohort_age"] = age
        if rolling:
            retained = (
                base.loc[base["last_ride_date"] >= base["cohort_date"] + pd.Timedelta(days=age)]
                .groupby("cohort_week", as_index=False)["user_id"]
                .nunique()
                .rename(columns={"user_id": "retained_users"})
            )
            retained["cohort_age"] = age
        else:
            retained = classic_numerator.loc[classic_numerator["cohort_age"].eq(age)]
        result = denominator.merge(retained, on=["cohort_week", "cohort_age"], how="left")
        result["retained_users"] = result["retained_users"].fillna(0).astype(int)
        result["retention"] = result["retained_users"] / result["eligible_users"]
        rows.append(result)
    return (
        pd.concat(rows, ignore_index=True)
        .sort_values(["cohort_week", "cohort_age"])
        .reset_index(drop=True)
    )


def milestone_retention(classic: pd.DataFrame, rolling: pd.DataFrame) -> pd.DataFrame:
    """Pivot the requested D1/D7/D30 measures by weekly cohort."""
    selected = [1, 7, 30]
    parts: list[pd.DataFrame] = []
    eligibility: pd.DataFrame | None = None
    for label, frame in (("classic", classic), ("rolling", rolling)):
        selected_frame = frame.loc[frame["cohort_age"].isin(selected)].copy()
        pivot = selected_frame.pivot(index="cohort_week", columns="cohort_age", values="retention")
        pivot.columns = [f"{label}_d{int(column)}" for column in pivot.columns]
        parts.append(pivot)
        if label == "classic":
            eligibility = selected_frame.pivot(
                index="cohort_week", columns="cohort_age", values="eligible_users"
            )
            eligibility.columns = [f"eligible_d{int(column)}" for column in eligibility.columns]
    if eligibility is None:  # defensive guard for future refactors
        raise ValueError("Classical retention is required for milestone eligibility")
    return pd.concat([*parts, eligibility], axis=1).reset_index().sort_values("cohort_week")


def early_outcomes(
    rides: pd.DataFrame, users: pd.DataFrame, data_end: pd.Timestamp
) -> pd.DataFrame:
    """Create a user-level analytic frame for the early-behaviour association."""
    ensure_columns(users, ["user_id", "acquisition_channel", "city"], "users")
    rides = rides.copy()
    rides["attempted_at"] = pd.to_datetime(rides["attempted_at"], utc=True, format="mixed")
    rides["completed_at"] = pd.to_datetime(rides["completed_at"], utc=True, format="mixed")
    cohorts = build_cohorts(rides)
    end_day = pd.Timestamp(data_end).tz_convert("UTC").tz_localize(None).normalize()
    eligible = cohorts.loc[cohorts["cohort_date"] + pd.Timedelta(days=30) <= end_day].copy()
    first_attempt = (
        rides.sort_values(["user_id", "attempted_at", "ride_id"])
        .groupby("user_id", as_index=False)
        .first()[["user_id", "status"]]
        .rename(columns={"status": "first_attempt_status"})
    )
    complete = completed_rides(rides)
    complete["ride_date"] = _day(complete["completed_at"])
    by_ride = complete.merge(eligible[["user_id", "cohort_date"]], on="user_id", how="inner")
    by_ride["cohort_age"] = (by_ride["ride_date"] - by_ride["cohort_date"]).dt.days
    early = (
        by_ride.loc[by_ride["cohort_age"].between(1, 7)]
        .groupby("user_id", as_index=False)["ride_id"]
        .nunique()
        .rename(columns={"ride_id": "rides_days_1_to_7"})
    )
    d30 = (
        by_ride.loc[by_ride["cohort_age"].eq(30)]
        .groupby("user_id", as_index=False)["ride_id"]
        .nunique()
        .assign(retained_d30_classic=1)[["user_id", "retained_d30_classic"]]
    )
    result = (
        eligible.merge(users[["user_id", "acquisition_channel", "city"]], on="user_id", how="inner")
        .merge(first_attempt, on="user_id", how="inner")
        .merge(early, on="user_id", how="left")
        .merge(d30, on="user_id", how="left")
    )
    result["rides_days_1_to_7"] = result["rides_days_1_to_7"].fillna(0).astype(int)
    result["retained_d30_classic"] = result["retained_d30_classic"].fillna(0).astype(int)
    result["early_activity_segment"] = pd.cut(
        result["rides_days_1_to_7"],
        bins=[-1, 0, 1, 3, np.inf],
        labels=["0", "1", "2–3", "4+"],
    ).astype(str)
    return result.sort_values("user_id").reset_index(drop=True)


def wilson_interval(
    successes: pd.Series | np.ndarray, totals: pd.Series | np.ndarray, z: float = 1.96
) -> tuple[np.ndarray, np.ndarray]:
    """Two-sided Wilson 95% interval for a binomial retention proportion."""
    successes_array = np.asarray(successes, dtype=float)
    totals_array = np.asarray(totals, dtype=float)
    proportions = np.divide(
        successes_array, totals_array, out=np.zeros_like(successes_array), where=totals_array > 0
    )
    denominator = 1 + z**2 / totals_array
    centre = (proportions + z**2 / (2 * totals_array)) / denominator
    radius = (
        z
        * np.sqrt((proportions * (1 - proportions) + z**2 / (4 * totals_array)) / totals_array)
        / denominator
    )
    return np.maximum(0, centre - radius), np.minimum(1, centre + radius)


def retention_by_segment(outcomes: pd.DataFrame, segment: str) -> pd.DataFrame:
    """D30 rate, sample size and Wilson confidence intervals by a preselected cut."""
    grouped = (
        outcomes.groupby(segment, observed=True, as_index=False)["retained_d30_classic"]
        .agg(retained_users="sum", eligible_users="count")
        .sort_values(segment)
        .reset_index(drop=True)
    )
    grouped["retention"] = grouped["retained_users"] / grouped["eligible_users"]
    low, high = wilson_interval(grouped["retained_users"], grouped["eligible_users"])
    grouped["ci_low"] = low
    grouped["ci_high"] = high
    return grouped


def quality_profile(
    users: pd.DataFrame, rides: pd.DataFrame, data_end: pd.Timestamp
) -> pd.DataFrame:
    """High-signal hard checks with explicit rates, suitable for the report."""
    end = pd.Timestamp(data_end)
    attempted = pd.to_datetime(rides["attempted_at"], utc=True, format="mixed")
    completed_at = pd.to_datetime(rides["completed_at"], utc=True, format="mixed")
    completed_mask = rides["status"].eq("completed")
    checks = [
        ("users.primary_key_unique", int(users["user_id"].duplicated().sum()), len(users)),
        ("rides.primary_key_unique", int(rides["ride_id"].duplicated().sum()), len(rides)),
        (
            "rides.user_foreign_key",
            int((~rides["user_id"].isin(users["user_id"])).sum()),
            len(rides),
        ),
        (
            "completed.completed_at_not_null",
            int((completed_mask & completed_at.isna()).sum()),
            int(completed_mask.sum()),
        ),
        (
            "failed.completed_at_null",
            int((~completed_mask & completed_at.notna()).sum()),
            int((~completed_mask).sum()),
        ),
        ("timestamps.not_after_data_end", int((attempted > end).sum()), len(rides)),
        (
            "completed_at.not_after_data_end",
            int((completed_mask & completed_at.gt(end)).sum()),
            int(completed_mask.sum()),
        ),
        (
            "status.accepted_values",
            int((~rides["status"].isin(["completed", "cancelled", "error"])).sum()),
            len(rides),
        ),
    ]
    profile = pd.DataFrame(checks, columns=["check", "failed_rows", "rows_checked"])
    profile["failure_rate"] = profile["failed_rows"] / profile["rows_checked"].replace(0, np.nan)
    profile["result"] = np.where(profile["failed_rows"].eq(0), "pass", "fail")
    return profile


def assert_quality(profile: pd.DataFrame) -> None:
    failures = profile.loc[profile["result"].ne("pass"), "check"].tolist()
    if failures:
        raise ValueError(f"Synthetic data quality checks failed: {failures}")


def create_sqlite_database(
    users: pd.DataFrame, rides: pd.DataFrame, database_path: Path, data_end: pd.Timestamp
) -> None:
    """Load source frames into a disposable SQLite database used by real SQL files."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if database_path.exists():
        database_path.unlink()
    with sqlite3.connect(database_path) as connection:
        users_to_write = users.copy()
        rides_to_write = rides.copy()
        for frame in (users_to_write, rides_to_write):
            for column in frame.select_dtypes(include=["datetimetz"]).columns:
                frame[column] = frame[column].astype(str)
        users_to_write.to_sql("users", connection, index=False)
        rides_to_write.to_sql("rides", connection, index=False)
        pd.DataFrame(
            [{"data_end_date": pd.Timestamp(data_end).tz_convert("UTC").date().isoformat()}]
        ).to_sql("analysis_parameters", connection, index=False)
        connection.executescript(
            "CREATE INDEX idx_rides_user_status ON rides(user_id, status);\n"
            "CREATE INDEX idx_rides_completed_at ON rides(completed_at);"
        )


def run_sql_file(database_path: Path, sql_path: Path) -> pd.DataFrame:
    """Execute one SELECT-only analysis file and return its reviewed result."""
    query = sql_path.read_text(encoding="utf-8")
    with sqlite3.connect(database_path) as connection:
        return pd.read_sql_query(query, connection)
