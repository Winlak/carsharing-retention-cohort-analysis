"""Build a deterministic, self-contained HTML handoff for five case charts.

The local pipeline also renders Matplotlib SVG files in ``figures/``. Those
files are useful when working locally but font layout differs by operating
system. This module serializes the same reviewed aggregates directly into SVG
markup, so the versioned handoff is byte-stable across CI platforms.
"""

from __future__ import annotations

import math
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

INK = "#183B56"
BLUE = "#2D6A9F"
GOLD = "#D09B2C"
ROSE = "#A9445B"
GRID = "#D9E1E8"
MUTED = "#5B6B7A"
EMPTY = "#EEF2F5"


def _n(value: float) -> str:
    """Format coordinates without platform-dependent representations."""
    return f"{float(value):.3f}".rstrip("0").rstrip(".")


def _rate(value: float) -> str:
    return f"{float(value):.1%}"


def _color(value: float) -> str:
    """Interpolate a restrained blue scale without a plotting backend."""
    low = (244, 247, 250)
    high = (45, 106, 159)
    fraction = min(max(float(value) / 0.25, 0.0), 1.0)
    rgb = [round(start + (end - start) * fraction) for start, end in zip(low, high)]
    return "#" + "".join(f"{channel:02x}" for channel in rgb)


def _polyline(points: list[tuple[float, float]], *, color: str, dash: str | None = None) -> str:
    attrs = f' stroke-dasharray="{dash}"' if dash else ""
    coordinates = " ".join(f"{_n(x)},{_n(y)}" for x, y in points)
    return (
        f'<polyline points="{coordinates}" fill="none" stroke="{color}" stroke-width="2.5"{attrs}/>'
    )


def _heatmap(frame: pd.DataFrame) -> str:
    width, height = 1120, 720
    left, top, right, bottom = 130, 38, 1030, 648
    weeks = sorted(pd.to_datetime(frame["cohort_week"]).unique())
    ages = list(range(1, 61))
    lookup = {
        (pd.Timestamp(row.cohort_week), int(row.cohort_age)): row.retention
        for row in frame.itertuples(index=False)
    }
    cell_width = (right - left) / len(ages)
    cell_height = (bottom - top) / len(weeks)
    marks: list[str] = [
        f'<rect x="{left}" y="{top}" width="{right - left}" height="{bottom - top}" fill="{EMPTY}"/>'
    ]
    for row_index, week in enumerate(weeks):
        for column_index, age in enumerate(ages):
            value = lookup.get((pd.Timestamp(week), age), np.nan)
            fill = EMPTY if pd.isna(value) else _color(float(value))
            marks.append(
                f'<rect x="{_n(left + column_index * cell_width)}" '
                f'y="{_n(top + row_index * cell_height)}" width="{_n(cell_width + 0.02)}" '
                f'height="{_n(cell_height + 0.02)}" fill="{fill}"/>'
            )
    labels: list[str] = []
    for age in range(0, 61, 7):
        x = left + min(age, 60) * cell_width - 3
        labels.append(f'<text x="{_n(x)}" y="{bottom + 20}" class="tick">{age}</text>')
    for index, week in enumerate(weeks):
        if index % 4 == 0 or index == len(weeks) - 1:
            y = top + (index + 0.7) * cell_height
            labels.append(
                f'<text x="12" y="{_n(y)}" class="tick">{pd.Timestamp(week).strftime("%d.%m.%y")}</text>'
            )
    legend_x = 810
    legend = [
        f'<rect x="{legend_x}" y="674" width="18" height="12" fill="{EMPTY}"/>',
        f'<text x="{legend_x + 24}" y="685" class="legend">не достигли age</text>',
    ]
    for index in range(5):
        legend.append(
            f'<rect x="{legend_x + 170 + index * 24}" y="674" width="24" height="12" '
            f'fill="{_color(index / 4 * 0.25)}"/>'
        )
    legend.extend(
        [
            f'<text x="{legend_x + 164}" y="704" class="legend">0%</text>',
            f'<text x="{legend_x + 252}" y="704" class="legend">≥25%</text>',
        ]
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Когортная матрица retention">'
        f'<text x="{left}" y="18" class="axis">Неделя первой завершённой поездки</text>'
        f'<text x="{left}" y="{bottom + 48}" class="axis">Cohort age, дней после первой поездки</text>'
        + "".join(marks + labels + legend)
        + "</svg>"
    )


def _retention_curves(classic: pd.DataFrame, rolling: pd.DataFrame) -> str:
    width, height = 1120, 440
    left, top, right, bottom = 74, 30, 1050, 344

    def point(age: float, value: float) -> tuple[float, float]:
        return left + age / 60 * (right - left), bottom - value * (bottom - top)

    grid = []
    for percent in range(0, 101, 25):
        y = bottom - percent / 100 * (bottom - top)
        grid.extend(
            [
                f'<line x1="{left}" x2="{right}" y1="{_n(y)}" y2="{_n(y)}" class="grid"/>',
                f'<text x="8" y="{_n(y + 4)}" class="tick">{percent}%</text>',
            ]
        )
    for age in range(0, 61, 10):
        x, _ = point(age, 0)
        grid.append(f'<text x="{_n(x - 5)}" y="{bottom + 22}" class="tick">{age}</text>')
    classic_points = [
        point(row.cohort_age, row.classical_retention) for row in classic.itertuples()
    ]
    rolling_points = [point(row.cohort_age, row.rolling_retention) for row in rolling.itertuples()]
    classic_low = [point(row.cohort_age, row.ci_low) for row in classic.itertuples()]
    classic_high = [point(row.cohort_age, row.ci_high) for row in classic.itertuples()]
    rolling_low = [point(row.cohort_age, row.ci_low) for row in rolling.itertuples()]
    rolling_high = [point(row.cohort_age, row.ci_high) for row in rolling.itertuples()]
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Classical и rolling retention">'
        + "".join(grid)
        + _polyline(classic_low, color=BLUE, dash="4 4")
        + _polyline(classic_high, color=BLUE, dash="4 4")
        + _polyline(rolling_low, color=GOLD, dash="4 4")
        + _polyline(rolling_high, color=GOLD, dash="4 4")
        + _polyline(classic_points, color=BLUE)
        + _polyline(rolling_points, color=GOLD)
        + f'<line x1="{left}" x2="{right}" y1="{bottom}" y2="{bottom}" class="axis-line"/>'
        + f'<line x1="{left}" x2="{left}" y1="{top}" y2="{bottom}" class="axis-line"/>'
        + f'<line x1="{left}" x2="{left + 28}" y1="390" y2="390" stroke="{BLUE}" stroke-width="3"/>'
        + f'<text x="{left + 36}" y="394" class="legend">Classical: активен ровно в D&lt;N&gt;</text>'
        + f'<line x1="{left + 330}" x2="{left + 358}" y1="390" y2="390" stroke="{GOLD}" stroke-width="3"/>'
        + f'<text x="{left + 366}" y="394" class="legend">Rolling: последняя активность в D&lt;N&gt; или позже</text>'
        + "</svg>"
    )


def _bar_chart(frame: pd.DataFrame, category: str, title: str) -> str:
    width, height = 1120, 440
    left, top, right, bottom = 74, 38, 1050, 322
    maximum = max(0.1, math.ceil(float(frame["ci_high"].max()) * 20) / 20)
    slots = len(frame)
    slot_width = (right - left) / slots
    bar_width = min(120, slot_width * 0.5)
    grid: list[str] = []
    for index in range(5):
        value = maximum * index / 4
        y = bottom - value / maximum * (bottom - top)
        grid.extend(
            [
                f'<line x1="{left}" x2="{right}" y1="{_n(y)}" y2="{_n(y)}" class="grid"/>',
                f'<text x="8" y="{_n(y + 4)}" class="tick">{value:.0%}</text>',
            ]
        )
    bars: list[str] = []
    for index, row in enumerate(frame.itertuples(index=False)):
        x = left + slot_width * (index + 0.5)
        height_value = float(row.retention) / maximum * (bottom - top)
        y = bottom - height_value
        low_y = bottom - float(row.ci_low) / maximum * (bottom - top)
        high_y = bottom - float(row.ci_high) / maximum * (bottom - top)
        label = escape(str(getattr(row, category)))
        bars.extend(
            [
                f'<rect x="{_n(x - bar_width / 2)}" y="{_n(y)}" width="{_n(bar_width)}" '
                f'height="{_n(height_value)}" fill="{BLUE}"/>',
                f'<line x1="{_n(x)}" x2="{_n(x)}" y1="{_n(low_y)}" y2="{_n(high_y)}" class="ci"/>',
                f'<line x1="{_n(x - 6)}" x2="{_n(x + 6)}" y1="{_n(low_y)}" y2="{_n(low_y)}" class="ci"/>',
                f'<line x1="{_n(x - 6)}" x2="{_n(x + 6)}" y1="{_n(high_y)}" y2="{_n(high_y)}" class="ci"/>',
                f'<text x="{_n(x)}" y="{_n(max(22, high_y - 8))}" text-anchor="middle" class="value">{_rate(row.retention)}</text>',
                f'<text x="{_n(x)}" y="{bottom + 22}" text-anchor="middle" class="tick">{label}</text>',
                f'<text x="{_n(x)}" y="{bottom + 39}" text-anchor="middle" class="small">n={int(row.eligible_users):,}</text>',
            ]
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">'
        + "".join(grid + bars)
        + f'<line x1="{left}" x2="{right}" y1="{bottom}" y2="{bottom}" class="axis-line"/>'
        + f'<line x1="{left}" x2="{left}" y1="{top}" y2="{bottom}" class="axis-line"/>'
        + '<text x="74" y="414" class="note">Столбцы — classical D30; линии — двусторонние Wilson 95% CI.</text>'
        + "</svg>"
    )


def _gap_histogram(intervals: pd.DataFrame, summary: pd.DataFrame) -> str:
    width, height = 1120, 440
    left, top, right, bottom = 74, 36, 1050, 316
    gaps = intervals.loc[intervals["gap_days"].notna() & intervals["gap_days"].le(60), "gap_days"]
    counts = [int(((gaps >= start) & (gaps < start + 2)).sum()) for start in range(0, 60, 2)]
    ceiling = max(1, math.ceil(max(counts) / 500) * 500)
    slot_width = (right - left) / len(counts)
    marks: list[str] = []
    for index in range(5):
        value = ceiling * index / 4
        y = bottom - value / ceiling * (bottom - top)
        marks.extend(
            [
                f'<line x1="{left}" x2="{right}" y1="{_n(y)}" y2="{_n(y)}" class="grid"/>',
                f'<text x="8" y="{_n(y + 4)}" class="tick">{int(value):,}</text>',
            ]
        )
    for index, count in enumerate(counts):
        x = left + index * slot_width
        bar_height = count / ceiling * (bottom - top)
        marks.append(
            f'<rect x="{_n(x + 1)}" y="{_n(bottom - bar_height)}" width="{_n(slot_width - 2)}" '
            f'height="{_n(bar_height)}" fill="{BLUE}"/>'
        )
    for day in range(0, 61, 10):
        x = left + day / 60 * (right - left)
        marks.append(f'<text x="{_n(x - 4)}" y="{bottom + 22}" class="tick">{day}</text>')
    median = float(summary.loc[summary["metric"].eq("median_gap_days"), "value"].iloc[0])
    short_share = float(summary.loc[summary["metric"].eq("share_gap_7d_or_less"), "value"].iloc[0])
    median_x = left + median / 60 * (right - left)
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Распределение интервалов между поездками">'
        + "".join(marks)
        + f'<line x1="{_n(median_x)}" x2="{_n(median_x)}" y1="{top}" y2="{bottom}" stroke="{GOLD}" stroke-width="3"/>'
        + f'<text x="{_n(median_x + 8)}" y="{top + 16}" class="value">медиана {median:.1f} дня</text>'
        + f'<line x1="{left}" x2="{right}" y1="{bottom}" y2="{bottom}" class="axis-line"/>'
        + f'<line x1="{left}" x2="{left}" y1="{top}" y2="{bottom}" class="axis-line"/>'
        + f'<text x="{left}" y="390" class="note">Бины по 2 дня; {short_share:.1%} наблюдаемых интервалов не длиннее недели; интервалы &gt;60 дней не показаны.</text>'
        + "</svg>"
    )


def build_visual_handoff(outputs: dict[str, pd.DataFrame], destination: Path) -> None:
    """Write a tracked HTML evidence handoff from already-validated aggregates."""
    classic = outputs["classical_cohort_matrix"]
    retention_curves = _retention_curves(outputs["classical_curve"], outputs["rolling_curve"])
    early_bars = _bar_chart(
        outputs["early_week_d30"], "early_activity_segment", "D30 по ранней активности"
    )
    experience_bars = _bar_chart(
        outputs["first_experience_d30"], "first_attempt_status", "D30 по первой попытке"
    )
    gaps = _gap_histogram(outputs["sql_intervals"], outputs["gap_summary"])
    cards = [
        (
            "cohort-heatmap",
            "Когортная матрица classical retention",
            "Недели активации × cohort age; серое поле — ещё не eligible.",
            _heatmap(classic),
        ),
        (
            "retention-curves",
            "Classical и rolling retention",
            "Агрегировано по eligible пользователям; пунктир — Wilson 95% CI.",
            retention_curves,
        ),
        (
            "early-week",
            "D30 и повторные поездки в D1–D7",
            "Early exposure исключает D0 и D30; это observational association.",
            early_bars,
        ),
        (
            "first-experience",
            "D30 и исход первой попытки",
            "Срез среди активировавшихся пользователей; возможен selection/collider bias.",
            experience_bars,
        ),
        (
            "ride-gaps",
            "Интервалы между завершёнными поездками",
            "Распределение построено из SQL-окна LAG() для completed rides.",
            gaps,
        ),
    ]
    rendered_cards = "".join(
        f'<section id="{card_id}" class="card"><h2>{escape(title)}</h2><p>{escape(subtitle)}</p>{svg}</section>'
        for card_id, title, subtitle, svg in cards
    )
    document = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Когорты, retention и повторные поездки — визуализации</title>
<style>
:root {{ color-scheme: light; font-family: Arial, sans-serif; color: {INK}; background: #f6f8fa; }}
body {{ margin: 0; }} main {{ max-width: 1180px; margin: 0 auto; padding: 36px 20px 56px; }}
h1 {{ margin: 0 0 8px; font-size: 30px; }} h2 {{ margin: 0 0 5px; font-size: 20px; }}
p {{ color: {MUTED}; line-height: 1.45; margin: 0 0 18px; }} .card {{ background: white; border: 1px solid {GRID}; border-radius: 10px; padding: 22px; margin-top: 20px; overflow-x: auto; }}
svg {{ min-width: 820px; width: 100%; height: auto; display: block; }} .grid {{ stroke: {GRID}; stroke-width: 1; }} .axis-line, .ci {{ stroke: {INK}; stroke-width: 1.2; }}
.tick {{ fill: {MUTED}; font-size: 12px; }} .legend, .axis {{ fill: {INK}; font-size: 13px; }} .value {{ fill: {INK}; font-size: 13px; font-weight: 700; }} .small, .note {{ fill: {MUTED}; font-size: 12px; }}
.meta {{ max-width: 840px; }}
</style>
</head>
<body><main>
<h1>Когорты, retention и повторные поездки</h1>
<p class="meta">Пять versioned visualizations из воспроизводимой синтетической симуляции. Это не данные Делимобиля или другого оператора. Источник: SQL/pandas outputs, seed 20240801.</p>
{rendered_cards}
</main></body></html>
"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")
