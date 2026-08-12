"""Build a compact reader-facing notebook from the executed pipeline outputs."""

from __future__ import annotations

import sys
from pathlib import Path

import nbformat as nbf
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _value(frame: pd.DataFrame, age: int, column: str) -> float:
    return float(frame.loc[frame["cohort_age"].eq(age), column].iloc[0])


def main() -> None:
    outputs_dir = ROOT / "outputs"
    classic_curve = pd.read_csv(outputs_dir / "classical_curve.csv")
    rolling_curve = pd.read_csv(outputs_dir / "rolling_curve.csv")
    early = pd.read_csv(outputs_dir / "early_week_d30.csv")
    early_0 = float(
        early.loc[early["early_activity_segment"].astype(str).eq("0"), "retention"].iloc[0]
    )
    early_4 = float(
        early.loc[early["early_activity_segment"].astype(str).eq("4+"), "retention"].iloc[0]
    )
    d30 = _value(classic_curve, 30, "classical_retention")
    rolling_d30 = _value(rolling_curve, 30, "rolling_retention")

    notebook = nbf.v4.new_notebook()
    notebook.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"},
    }
    notebook.cells = [
        nbf.v4.new_markdown_cell(
            "# Когорты, retention и повторные поездки\n\n"
            "Репродуцируемый pandas + SQLite разбор синтетической истории каршеринга. "
            "Данные генерируются локально: это не наблюдения реального оператора."
        ),
        nbf.v4.new_markdown_cell(
            "## tl;dr\n\n"
            f"В текущем воспроизводимом прогоне classical D30 равен **{d30:.1%}**, а rolling D30 — **{rolling_d30:.1%}**. "
            f"У пользователей с 4+ завершёнными поездками на D1–D7 classical D30 составляет **{early_4:.1%}** "
            f"против **{early_0:.1%}** у сегмента без повторной поездки. Это сильная описательная ассоциация, "
            "но не causal effect: early activity и D30 имеют общие причины."
        ),
        nbf.v4.new_markdown_cell(
            "## Context & Methods\n\n"
            "### Key Assumptions\n\n"
            "- Cohort date — дата первой **completed** поездки, а не регистрации или первой попытки.\n"
            "- Classical D<N> требует completed ride ровно в N-й день; rolling D<N> — последней активности в N-й день или позже.\n"
            "- Для каждого N в denominator остаются только пользователи с наблюдаемым `cohort_date + N`.\n"
            "- Признак первой недели — completed rides в D1–D7; D30 исключён, чтобы не создать data leakage."
        ),
        nbf.v4.new_markdown_cell("## Data\n\n### 1. Load generated inputs"),
        nbf.v4.new_code_cell(
            "from pathlib import Path\n"
            "import sys\n"
            "import matplotlib.pyplot as plt\n"
            "import numpy as np\n"
            "import pandas as pd\n"
            "import seaborn as sns\n\n"
            "ROOT = next((candidate for candidate in [Path.cwd(), *Path.cwd().parents] if (candidate / 'src').exists()), None)\n"
            "if ROOT is None:\n"
            "    raise RuntimeError('Could not locate repository root; run `make all` first.')\n"
            "sys.path.insert(0, str(ROOT))\n"
            "from src.metrics import (cohort_retention, early_outcomes, retention_by_segment, run_sql_file, wilson_interval)\n\n"
            "users = pd.read_csv(ROOT / 'data/generated/users.csv')\n"
            "rides = pd.read_csv(ROOT / 'data/generated/rides.csv')\n"
            "users['registered_at'] = pd.to_datetime(users['registered_at'], utc=True, format='mixed')\n"
            "for column in ['attempted_at', 'started_at', 'completed_at']:\n"
            "    rides[column] = pd.to_datetime(rides[column], utc=True, format='mixed')\n"
            "data_end = pd.Timestamp('2024-12-31 23:59:59+00:00')\n"
            "users.head(), rides.head()"
        ),
        nbf.v4.new_code_cell(
            "# Filter to behavioural events and build first-completed-ride cohorts with pandas groupby.\n"
            "completed = rides.loc[rides['status'].eq('completed')].copy()\n"
            "completed['ride_date'] = pd.to_datetime(completed['completed_at'], utc=True).dt.normalize().dt.tz_localize(None)\n"
            "cohorts = (completed.groupby('user_id', as_index=False)['ride_date'].min()\n"
            "           .rename(columns={'ride_date': 'cohort_date'}))\n"
            "cohorts['cohort_week'] = cohorts['cohort_date'] - pd.to_timedelta(cohorts['cohort_date'].dt.weekday, unit='D')\n"
            "cohort_events = completed.merge(cohorts, on='user_id', how='inner')\n"
            "cohort_events['cohort_age'] = (cohort_events['ride_date'] - cohort_events['cohort_date']).dt.days\n"
            "print(f'registrations={len(users):,}; completed rides={len(completed):,}; activated users={len(cohorts):,}')\n"
            "cohort_events[['user_id', 'ride_date', 'cohort_date', 'cohort_age']].head()"
        ),
        nbf.v4.new_markdown_cell("### 2. Verify SQL implementation and calculate cohort matrices"),
        nbf.v4.new_code_cell(
            "# The SQL queries use CTEs/JOINs; this cell reads their actual SQLite result.\n"
            "sqlite_path = ROOT / 'data/generated/analysis.sqlite'\n"
            "sql_matrix = run_sql_file(sqlite_path, ROOT / 'sql/cohort_retention.sql')\n"
            "sql_matrix.head()"
        ),
        nbf.v4.new_code_cell(
            "# Independent pandas calculation; it is compared with SQL in scripts/run_pipeline.py.\n"
            "classical = cohort_retention(rides, data_end, max_age=60, rolling=False)\n"
            "rolling = cohort_retention(rides, data_end, max_age=60, rolling=True)\n"
            "(classical.head(), rolling.head())"
        ),
        nbf.v4.new_markdown_cell("## Results\n\n### 3. Cohort heatmap"),
        nbf.v4.new_code_cell(
            "heatmap = classical.pivot(index='cohort_week', columns='cohort_age', values='retention')\n"
            "plt.figure(figsize=(14, 10))\n"
            "sns.heatmap(heatmap * 100, cmap=sns.light_palette('#2D6A9F', as_cmap=True), vmin=0, cbar_kws={'label': 'Classical retention, %'})\n"
            "plt.title('Classical retention by weekly cohort and cohort age')\n"
            "plt.xlabel('Cohort age, days')\n"
            "plt.ylabel('Cohort week')\n"
            "plt.show()"
        ),
        nbf.v4.new_code_cell(
            "# Aggregate eligible numerators/denominators before computing curves and Wilson CIs.\n"
            "def curve(frame, label):\n"
            "    result = frame.groupby('cohort_age', as_index=False)[['eligible_users', 'retained_users']].sum()\n"
            "    result[label] = result['retained_users'] / result['eligible_users']\n"
            "    result['ci_low'], result['ci_high'] = wilson_interval(result['retained_users'], result['eligible_users'])\n"
            "    return result\n\n"
            "classic_curve = curve(classical, 'classical')\n"
            "rolling_curve = curve(rolling, 'rolling')\n"
            "fig, ax = plt.subplots(figsize=(11, 5))\n"
            "for frame, column, color, label in [(classic_curve, 'classical', '#2D6A9F', 'Classical'), (rolling_curve, 'rolling', '#D09B2C', 'Rolling')]:\n"
            "    ax.plot(frame['cohort_age'], frame[column] * 100, color=color, label=label)\n"
            "    ax.fill_between(frame['cohort_age'], frame['ci_low'] * 100, frame['ci_high'] * 100, color=color, alpha=.14)\n"
            "ax.set(title='Retention curves with Wilson 95% CI', xlabel='Cohort age, days', ylabel='Retention, %')\n"
            "ax.set_ylim(bottom=0); ax.legend(); ax.grid(axis='y', alpha=.25)\n"
            "plt.show()"
        ),
        nbf.v4.new_markdown_cell("### 4. Segmentation: first week and first-attempt experience"),
        nbf.v4.new_code_cell(
            "outcomes = early_outcomes(rides, users, data_end)\n"
            "early_segment = retention_by_segment(outcomes, 'early_activity_segment')\n"
            "first_attempt_segment = retention_by_segment(outcomes, 'first_attempt_status')\n"
            "early_segment, first_attempt_segment"
        ),
        nbf.v4.new_code_cell(
            "plot_data = early_segment.copy()\n"
            "plot_data['early_activity_segment'] = pd.Categorical(plot_data['early_activity_segment'], ['0', '1', '2–3', '4+'], ordered=True)\n"
            "plot_data = plot_data.sort_values('early_activity_segment')\n"
            "x = np.arange(len(plot_data)); y = plot_data['retention'].to_numpy() * 100\n"
            "fig, ax = plt.subplots(figsize=(8, 4.8))\n"
            "ax.bar(x, y, color='#2D6A9F')\n"
            "ax.errorbar(x, y, yerr=np.vstack([y - plot_data['ci_low'].to_numpy()*100, plot_data['ci_high'].to_numpy()*100 - y]), fmt='none', color='#183B56', capsize=4)\n"
            "ax.set(xticks=x, xticklabels=plot_data['early_activity_segment'], ylabel='Classical D30, %', title='D30 by completed rides in days 1–7')\n"
            "ax.grid(axis='y', alpha=.25)\n"
            "plt.show()"
        ),
        nbf.v4.new_markdown_cell("### 5. Frequency and gaps with SQL window functions"),
        nbf.v4.new_code_cell(
            "intervals = run_sql_file(sqlite_path, ROOT / 'sql/ride_frequency_and_gaps.sql')\n"
            "gaps = intervals.loc[intervals['gap_days'].notna(), 'gap_days']\n"
            "print(f'Median gap: {gaps.median():.1f} days; P75: {gaps.quantile(.75):.1f} days')\n"
            "intervals[['user_id', 'completed_ride_number', 'previous_completed_at', 'gap_days']].head(10)"
        ),
        nbf.v4.new_markdown_cell(
            "## Takeaways\n\n"
            "1. Повторная completed ride в первую неделю — сильный приоритизатор для CRM, но не доказательство того, что CRM создаст весь observed lift.\n"
            "2. Первая ошибка/отмена требует отдельной воронки registration → first attempt → first completed ride; conditioning только на activated users создаёт selection bias.\n"
            "3. Эксперимент нужно назначать на `user_id` до показа триггера и оценивать ITT на заранее заданном D30 с guardrails. Детали — в `docs/experiment_design.md`."
        ),
    ]
    path = ROOT / "notebooks" / "carsharing_retention_case.ipynb"
    nbf.write(notebook, path)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
