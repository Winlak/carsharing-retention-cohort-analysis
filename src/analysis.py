"""Pandas analysis, confidence intervals, and saved portfolio visualizations."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from src.metrics import (
    cohort_retention,
    early_outcomes,
    milestone_retention,
    quality_profile,
    retention_by_segment,
    run_sql_file,
    wilson_interval,
)

PALETTE = {
    "navy": "#183B56",
    "blue": "#2D6A9F",
    "gold": "#D09B2C",
    "rose": "#A9445B",
    "grid": "#D9E1E8",
}


def _save(figure: plt.Figure, path: Path) -> None:
    figure.tight_layout()
    figure.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def _overall_curve(frame: pd.DataFrame, metric_name: str) -> pd.DataFrame:
    curve = frame.groupby("cohort_age", as_index=False)[["eligible_users", "retained_users"]].sum()
    curve[metric_name] = curve["retained_users"] / curve["eligible_users"]
    low, high = wilson_interval(curve["retained_users"], curve["eligible_users"])
    curve["ci_low"] = low
    curve["ci_high"] = high
    return curve


def _cohort_heatmap(classic: pd.DataFrame, path: Path) -> None:
    matrix = classic.pivot(index="cohort_week", columns="cohort_age", values="retention")
    # Age 0 is mechanically 100% because it defines the cohort. Excluding it
    # keeps the color scale honest and lets the reader inspect repeat activity.
    matrix = matrix.drop(columns=0, errors="ignore")
    matrix.index = pd.to_datetime(matrix.index).strftime("%d.%m.%Y")
    figure, axis = plt.subplots(figsize=(14, max(8, 0.24 * len(matrix))))
    sns.heatmap(
        matrix * 100,
        cmap=sns.light_palette(PALETTE["blue"], as_cmap=True),
        vmin=0,
        vmax=max(20, np.nanpercentile(matrix * 100, 98)),
        cbar_kws={"label": "Classical retention, %"},
        ax=axis,
    )
    axis.set_title(
        "Когортная матрица: classical retention по дням жизни", loc="left", weight="bold"
    )
    axis.set_xlabel("Cohort age, дни после первой завершённой поездки")
    axis.set_ylabel("Неделя первой завершённой поездки")
    _save(figure, path)


def _retention_curves(
    classic: pd.DataFrame, rolling: pd.DataFrame, path: Path
) -> tuple[pd.DataFrame, pd.DataFrame]:
    classic_curve = _overall_curve(classic, "classical_retention")
    rolling_curve = _overall_curve(rolling, "rolling_retention")
    figure, axis = plt.subplots(figsize=(11, 5.8))
    for curve, column, label, color in (
        (
            classic_curve,
            "classical_retention",
            "Classical: активен ровно в день N",
            PALETTE["blue"],
        ),
        (
            rolling_curve,
            "rolling_retention",
            "Rolling: последняя активность в день N или позже",
            PALETTE["gold"],
        ),
    ):
        axis.plot(curve["cohort_age"], curve[column] * 100, label=label, color=color, linewidth=2.4)
        axis.fill_between(
            curve["cohort_age"],
            curve["ci_low"] * 100,
            curve["ci_high"] * 100,
            color=color,
            alpha=0.13,
        )
    axis.set_title("Кривые удержания с 95% Wilson CI", loc="left", weight="bold")
    axis.set_xlabel("Cohort age, дни")
    axis.set_ylabel("Retention, % от eligible пользователей")
    axis.set_ylim(bottom=0)
    axis.grid(axis="y", color=PALETTE["grid"], linewidth=0.8)
    axis.legend(frameon=False, loc="upper right")
    _save(figure, path)
    return classic_curve, rolling_curve


def _interval_bars(frame: pd.DataFrame, category: str, title: str, path: Path, color: str) -> None:
    ordered = frame.copy()
    figure, axis = plt.subplots(figsize=(8.6, 5.1))
    positions = np.arange(len(ordered))
    values = ordered["retention"].to_numpy() * 100
    lower = values - ordered["ci_low"].to_numpy() * 100
    upper = ordered["ci_high"].to_numpy() * 100 - values
    bars = axis.bar(positions, values, color=color, width=0.62, edgecolor="#183B56", linewidth=0.7)
    axis.errorbar(
        positions,
        values,
        yerr=np.vstack([lower, upper]),
        fmt="none",
        ecolor="#183B56",
        capsize=4,
        linewidth=1.2,
    )
    axis.set_xticks(positions, ordered[category].astype(str))
    axis.set_ylabel("Classical D30, %")
    axis.set_title(title, loc="left", weight="bold")
    axis.set_ylim(0, max(5, (ordered["ci_high"].max() * 100) * 1.25))
    axis.grid(axis="y", color=PALETTE["grid"], linewidth=0.8)
    for bar, value, count in zip(bars, values, ordered["eligible_users"]):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.45,
            f"{value:.1f}%\nn={count:,}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    _save(figure, path)


def _gap_distribution(intervals: pd.DataFrame, path: Path) -> pd.DataFrame:
    gaps = intervals.loc[intervals["gap_days"].notna() & intervals["gap_days"].le(60), "gap_days"]
    summary = pd.DataFrame(
        {
            "metric": ["intervals", "median_gap_days", "p75_gap_days", "share_gap_7d_or_less"],
            "value": [len(gaps), gaps.median(), gaps.quantile(0.75), (gaps <= 7).mean()],
        }
    )
    figure, axis = plt.subplots(figsize=(9.4, 5.1))
    axis.hist(gaps, bins=np.arange(0, 62, 2), color=PALETTE["blue"], edgecolor="white")
    axis.axvline(
        gaps.median(), color=PALETTE["gold"], linewidth=2, label=f"Медиана: {gaps.median():.1f} дн."
    )
    axis.set_title("Интервалы между завершёнными поездками", loc="left", weight="bold")
    axis.set_xlabel("Дней с предыдущей завершённой поездки (интервалы >60 дней не показаны)")
    axis.set_ylabel("Количество интервалов")
    axis.grid(axis="y", color=PALETTE["grid"], linewidth=0.8)
    axis.legend(frameon=False)
    _save(figure, path)
    return summary


def run_analysis(
    users: pd.DataFrame,
    rides: pd.DataFrame,
    *,
    data_end: pd.Timestamp,
    sql_dir: Path,
    database_path: Path,
    figures_dir: Path,
    outputs_dir: Path,
) -> dict[str, pd.DataFrame]:
    """Run independent pandas and SQL analysis paths, then materialize evidence."""
    figures_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    profile = quality_profile(users, rides, data_end)
    classic = cohort_retention(rides, data_end, max_age=60, rolling=False)
    rolling = cohort_retention(rides, data_end, max_age=60, rolling=True)
    milestones = milestone_retention(classic, rolling)
    outcomes = early_outcomes(rides, users, data_end)
    early_segment = retention_by_segment(outcomes, "early_activity_segment")
    early_segment["early_activity_segment"] = pd.Categorical(
        early_segment["early_activity_segment"], categories=["0", "1", "2–3", "4+"], ordered=True
    )
    early_segment = early_segment.sort_values("early_activity_segment").reset_index(drop=True)
    experience_segment = retention_by_segment(outcomes, "first_attempt_status")
    channel_segment = retention_by_segment(outcomes, "acquisition_channel")
    city_segment = retention_by_segment(outcomes, "city")

    # Real SQL files are executed against the same generated source tables.
    sql_classic = run_sql_file(database_path, sql_dir / "cohort_retention.sql")
    sql_rolling = run_sql_file(database_path, sql_dir / "rolling_retention.sql")
    sql_milestones = run_sql_file(database_path, sql_dir / "retention_milestones.sql")
    sql_intervals = run_sql_file(database_path, sql_dir / "ride_frequency_and_gaps.sql")
    sql_outcomes = run_sql_file(database_path, sql_dir / "early_experience_d30.sql")
    for sql_frame in (sql_classic, sql_rolling, sql_milestones):
        sql_frame["cohort_week"] = pd.to_datetime(sql_frame["cohort_week"])

    # Independent cross-check: pandas and SQL use the same definitions but
    # distinct implementations, so a row-level mismatch stops the pipeline.
    pandas_classic = classic.rename(columns={"retention": "classical_retention"})
    compare = pandas_classic.merge(
        sql_classic, on=["cohort_week", "cohort_age"], suffixes=("_pd", "_sql")
    )
    if not np.allclose(
        compare["classical_retention_pd"], compare["classical_retention_sql"], atol=1e-6
    ):
        raise ValueError("Pandas and SQL classical retention disagree")
    pandas_rolling = rolling.rename(columns={"retention": "rolling_retention"})
    compare_rolling = pandas_rolling.merge(
        sql_rolling, on=["cohort_week", "cohort_age"], suffixes=("_pd", "_sql")
    )
    if not np.allclose(
        compare_rolling["rolling_retention_pd"], compare_rolling["rolling_retention_sql"], atol=1e-6
    ):
        raise ValueError("Pandas and SQL rolling retention disagree")
    if len(sql_outcomes) != len(outcomes):
        raise ValueError("SQL and pandas D30 eligibility populations disagree")

    _cohort_heatmap(classic, figures_dir / "cohort_heatmap.png")
    classic_curve, rolling_curve = _retention_curves(
        classic, rolling, figures_dir / "retention_curves.png"
    )
    _interval_bars(
        early_segment,
        "early_activity_segment",
        "D30 и количество завершённых поездок в дни 1–7",
        figures_dir / "early_week_vs_d30.png",
        PALETTE["blue"],
    )
    _interval_bars(
        experience_segment,
        "first_attempt_status",
        "D30 и исход первой попытки бронирования",
        figures_dir / "first_experience_vs_d30.png",
        PALETTE["rose"],
    )
    gap_summary = _gap_distribution(sql_intervals, figures_dir / "ride_gap_distribution.png")

    outputs = {
        "quality_checks": profile,
        "classical_cohort_matrix": classic,
        "rolling_cohort_matrix": rolling,
        "retention_milestones": milestones,
        "early_week_d30": early_segment,
        "first_experience_d30": experience_segment,
        "channel_d30": channel_segment,
        "city_d30": city_segment,
        "gap_summary": gap_summary,
        "classical_curve": classic_curve,
        "rolling_curve": rolling_curve,
        "sql_retention_milestones": sql_milestones,
        "sql_intervals": sql_intervals,
        "user_outcomes": outcomes,
    }
    for name, frame in outputs.items():
        if name in {"sql_intervals", "user_outcomes"}:
            continue
        frame.to_csv(outputs_dir / f"{name}.csv", index=False)
    return outputs
