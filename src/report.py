"""Render a Russian-language, evidence-backed Markdown report from analysis outputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def _rate(frame: pd.DataFrame, age: int, metric: str) -> tuple[float, int]:
    row = frame.loc[frame["cohort_age"].eq(age)].iloc[0]
    return float(row[metric]), int(row["eligible_users"])


def _segment_value(
    frame: pd.DataFrame, segment_column: str, segment: str
) -> tuple[float, int, float, float]:
    row = frame.loc[frame[segment_column].astype(str).eq(segment)].iloc[0]
    return (
        float(row["retention"]),
        int(row["eligible_users"]),
        float(row["ci_low"]),
        float(row["ci_high"]),
    )


def _segment_table(frame: pd.DataFrame, label: str) -> str:
    """Create an audit-friendly, compact Markdown table from a CI segment cut."""
    rows = [f"| {label} | eligible n | Classical D30 | 95% CI |", "|---|---:|---:|---:|"]
    for record in frame.itertuples(index=False):
        value = getattr(record, label)
        rows.append(
            f"| {value} | {record.eligible_users:,} | {record.retention:.1%} | "
            f"{record.ci_low:.1%}–{record.ci_high:.1%} |"
        )
    return "\n".join(rows)


def build_markdown_report(
    *,
    users: pd.DataFrame,
    rides: pd.DataFrame,
    outputs: dict[str, pd.DataFrame],
    data_end: pd.Timestamp,
    destination: Path,
) -> None:
    """Create the final technical report; values always come from executed frames."""
    classic_curve = outputs["classical_curve"]
    rolling_curve = outputs["rolling_curve"]
    early = outputs["early_week_d30"]
    experience = outputs["first_experience_d30"]
    channels = outputs["channel_d30"]
    cities = outputs["city_d30"]
    gap_summary = outputs["gap_summary"]
    quality = outputs["quality_checks"]

    classic_d1, d1_n = _rate(classic_curve, 1, "classical_retention")
    classic_d7, d7_n = _rate(classic_curve, 7, "classical_retention")
    classic_d30, d30_n = _rate(classic_curve, 30, "classical_retention")
    rolling_d30, _ = _rate(rolling_curve, 30, "rolling_retention")
    early_zero, early_zero_n, _, _ = _segment_value(early, "early_activity_segment", "0")
    early_four, early_four_n, early_four_low, early_four_high = _segment_value(
        early, "early_activity_segment", "4+"
    )
    first_complete, first_complete_n, _, _ = _segment_value(
        experience, "first_attempt_status", "completed"
    )
    first_cancelled, first_cancelled_n, _, _ = _segment_value(
        experience, "first_attempt_status", "cancelled"
    )
    first_error, first_error_n, _, _ = _segment_value(experience, "first_attempt_status", "error")
    median_gap = float(
        gap_summary.loc[gap_summary["metric"].eq("median_gap_days"), "value"].iloc[0]
    )
    short_gap_share = float(
        gap_summary.loc[gap_summary["metric"].eq("share_gap_7d_or_less"), "value"].iloc[0]
    )
    gap_pp = (early_four - early_zero) * 100
    quality_result = (
        f"все {len(quality):,} базовых проверок прошли"
        if quality["result"].eq("pass").all()
        else "есть сбои в checks — см. outputs/quality_checks.csv"
    )
    complete_attempts = int(rides["status"].eq("completed").sum())

    content = f"""# Когорты, retention и повторные поездки

## Техническое резюме

- **Вывод для продукта:** сильнейший наблюдаемый ранний сигнал — повторные завершённые поездки в дни 1–7. У сегмента с 4+ такими поездками D30 составляет **{early_four:.1%}** (95% CI {early_four_low:.1%}–{early_four_high:.1%}, n={early_four_n:,}) против **{early_zero:.1%}** у сегмента без повторной поездки (n={early_zero_n:,}); разница — **{gap_pp:.1f} п.п.**
- **Это не причинный эффект.** В симуляции и в реальном продукте ранняя активность совместно определяется намерением пользователя, каналом и городом. Поэтому CRM не следует «приписывать» весь разрыв сообщению или фиче без эксперимента.
- **Первая попытка важна как качество воронки:** D30 среди активировавшихся после успешной первой попытки — **{first_complete:.1%}** (n={first_complete_n:,}); после отмены — **{first_cancelled:.1%}** (n={first_cancelled_n:,}); после ошибки — **{first_error:.1%}** (n={first_error_n:,}). Это приоритет для проверки надёжности оплаты/доступности, а не доказательство её causal lift.
- **Масштаб и измерение:** {len(users):,} синтетических регистраций, {len(rides):,} попыток и {complete_attempts:,} завершённых поездок до {pd.Timestamp(data_end).date().isoformat()}. Aggregate D1 / D7 / D30 classical retention: **{classic_d1:.1%} / {classic_d7:.1%} / {classic_d30:.1%}**; знаменатели соответственно n={d1_n:,} / {d7_n:,} / {d30_n:,}.

> Данные и все значения в этом кейсе синтетические и воспроизводимо генерируются из seed. Они не являются данными Делимобиля или другого реального оператора.

## Удержание: один вопрос — два разных определения

**Classical retention в день N** — доля пользователей, у которых есть хотя бы одна *завершённая* поездка ровно в календарный день `cohort_date + N`.

**Rolling retention в день N** — доля пользователей, у которых последняя наблюдаемая завершённая поездка приходится на день N или позже (то есть они были активны хотя бы один раз после наступления N). На D30 он равен **{rolling_d30:.1%}** и не сопоставим по уровню с classical D30: вопрос другой.

**Cohort age** — число полных календарных дней между датой первой завершённой поездки и датой рассматриваемой активности. В знаменатель для D1/D7/D30 попадает только пользователь, для которого соответствующая дата уже наступила к `data_end`; поздние когорты не ошибочно маркируются как churned из-за right censoring.

![Когортная матрица](../figures/cohort_heatmap.svg)

На heatmap по строкам — неделя первой завершённой поездки, по столбцам — cohort age. Пустые правые ячейки — ещё не достигнутые возраста когорты, а не нули retention.

![Кривые retention](../figures/retention_curves.svg)

Classical кривая отвечает на вопрос «есть ли активность в конкретный день» и поэтому ниже и более шумная. Rolling кривая похожа на survival-оценку наблюдаемой активности: она монотонна по определению и должна читаться только вместе с возрастной eligibility.

## Первая неделя — полезный триггер, но не «доказанная причина»

![D30 по ранней активности](../figures/early_week_vs_d30.svg)

Сегменты заданы *до* D30: число завершённых поездок в дни 1–7 после первой завершённой поездки; D0 не входит в экспозицию. Столбцы показывают classical D30, линии — двусторонние Wilson 95% CI. Таким образом, здесь нет механического data leakage из дня 30 в ранний признак.

Интерпретация для CRM: отсутствие второй поездки в первую неделю — разумный **триггер для эксперимента**, а не сегмент, для которого можно заявить ожидаемый causal lift. Пользователи с высокой исходной потребностью и удобными маршрутами одновременно чаще совершают ранние поездки и возвращаются позднее; часть этого намерения не наблюдается в продуктовых логах.

## Фрикция первой попытки и частота повторов

![D30 по первому опыту](../figures/first_experience_vs_d30.svg)

Статус первой попытки бронирования задан до cohort date. Этот срез ограничен пользователями, которые всё же активировались первой завершённой поездкой; поэтому он дополнительно подвержен **selection/collider bias**: часть пользователей после неудачи не дошла до активации и исключена из retention-когорты. Для измерения полного влияния фрикции нужно отдельно мониторить регистрацию → первую попытку → первую завершённую поездку.

![Интервалы между поездками](../figures/ride_gap_distribution.svg)

Медианный интервал между двумя завершёнными поездками — **{median_gap:.1f} дня**; **{short_gap_share:.1%}** интервалов не длиннее недели. SQL использует `ROW_NUMBER()` для нумерации поездок пользователя и `LAG()` для расчёта интервалов, а pandas агрегирует распределения и сегменты.

## Контекст привлечения: наблюдаемая неоднородность

Канал и город — pre-treatment признаки, поэтому их полезно сохранять в assignment и разрезах A/B-теста. Эти таблицы описывают **не скорректированные** D30 rates; они не доказывают, что сам канал или город вызывает разницу. Но они показывают, почему агрегированная связь ранней активности с D30 может смешивать разные типы пользователей и операционные условия.

{_segment_table(channels, "acquisition_channel")}

{_segment_table(cities, "city")}

## Данные, проверки и определения

**Источник:** [`scripts/generate_data.py`](../scripts/generate_data.py) с фиксированным seed `20240801`; лицензия кода — [MIT](../LICENSE). В генераторе нет персональных данных, а скрытая propensity не сохраняется в CSV намеренно: она моделирует остаточное смешение, которое аналитик обычно не может наблюдать.

**Гранулярность:** `users` — одна строка на регистрацию; `rides` — одна попытка бронирования. В retention участвуют только строки `status = completed`; отмена и ошибка остаются в `rides` для описания first-ride experience. Полное описание полей — в [`docs/data_dictionary.md`](../docs/data_dictionary.md).

**Качество входа:** {quality_result}. Проверяются уникальность ключей, referential integrity, допустимые статусы, временная граница, обязательность `completed_at` у завершённых попыток и его отсутствие у неуспешных. Результат хранится в [`outputs/quality_checks.csv`](../outputs/quality_checks.csv).

**Две независимые реализации:** SQL из [`sql/`](../sql) выполняется в SQLite, а pandas повторяет cohort calculations. Pipeline останавливается, если классическая или rolling матрица не совпадает с SQL до `1e-6`, либо не совпадает D30-eligible population.

## Что проверять следующим экспериментом

1. **CRM для «нет второй поездки к D3».** Рандомизировать eligible активированных пользователей на control и один конкретный стимул: персональный маршрутный сценарий *или* кредит на следующую поездку (не смешивать механики). Основная метрика — classical D30; вторичные — rolling D30, поездки D1–7 и вклад в валовую маржу. Guardrails: отмены, payment errors, скидка на завершённую поездку, обращения в поддержку.
2. **Recovery первой ошибки.** При платёжной/разблокировочной ошибке рандомизировать понятный recovery flow: повтор оплаты/другая машина с сохранёнными параметрами против текущего опыта. Primary — first-completed-ride conversion за 24 часа; затем D30 среди всех назначенных пользователей (ITT), а не только активированных.
3. **Экспериментальный дизайн.** Единица рандомизации — `user_id`, assignment до показа триггера, один вариант на пользователя, стратификация по городу и acquisition channel. Предварительно зафиксировать окно наблюдения, исключения, остановку и multiple-metric policy. Анализировать ITT, публиковать effect size и 95% CI; не «переключать» метрику с D30 на более красивую постфактум.

## Ограничения и robustness checks

- Это синтетическая симуляция: её числа иллюстрируют метод, а не размер реальной возможности рынка.
- Связи ранней активности/первой попытки с D30 observational. Скрытая propensity, сезонность, доступность машин, цены, маршруты и коммуникации могут менять оценку; разрезы города и канала уменьшают, но не устраняют смешение.
- Classical retention чувствителен к календарному дню: пользователь с поездкой на D29 и D31 не retained на exact D30. Rolling менее строг, но отвечает на другой вопрос и зависит от окна наблюдения.
- Right censoring обрабатывается eligibility по каждому age; поэтому cohort size меняется вправо на матрице. Сравнивать когорты следует на общем наблюдаемом age, а не на «последней доступной» колонке.
- Для устойчивости pipeline сопоставляет SQL и pandas, использует Wilson CI вместо normal approximation и тестирует отсутствие D30 в признаке первых 7 дней. Это не заменяет A/B test.

## Следующие вопросы

- Как различаются first-completed-ride conversion и D30 по причинам отмены/ошибки, а не только по их общему статусу?
- Меняется ли эффект CRM по доступности машин рядом с пользователем, цене и типичному маршруту? Эти переменные нужны до назначения, чтобы избежать post-treatment segmentation.
- Какова unit economics-инкрементальность повторной поездки и размер скидки, при котором D30 lift окупается?
"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
