# Когорты, retention и повторные поездки

Портфолио-кейс продуктового аналитика о том, как измерять удержание в каршеринге, читать когорты и честно проверять связь first-ride experience с будущими поездками.

> Важно: данные полностью синтетические, генерируются локально из фиксированного seed и не относятся к Делимобилю или любому реальному оператору.

## Бизнес-вопрос

Какие наблюдаемые сигналы первой недели и первой попытки бронирования стоит превратить в проверяемые CRM/product-гипотезы для роста повторных поездок — и где заканчивается описательная аналитика и начинается необходимость эксперимента?

Полный ответ с цифрами текущего воспроизводимого прогона — в [аналитическом отчёте](reports/analytical_report.md). Пять versioned визуализаций без зависимости от графического backend — в [self-contained HTML handoff](docs/visualization_handoff.html). Для интерактивного разбора кода и вычислений — [ноутбук](notebooks/carsharing_retention_case.ipynb).

## Что внутри

```text
├── scripts/                 # генератор, pipeline и сборка ноутбука
├── src/                     # метрики, pandas-анализ, графики, отчёт
├── sql/                     # SQLite-запросы: CTE, JOIN, агрегации, оконные функции
├── tests/                   # проверки метрик, eligibility и SQL/pandas cross-check
├── docs/                    # data dictionary и методология эксперимента
├── figures/                 # сохранённые графики
├── outputs/                 # компактные результаты расчётов
└── reports/                 # читабельный аналитический отчёт
```

## Метрики: прежде чем смотреть на проценты

- **Cohort** — пользователи, сгруппированные по неделе их первой *завершённой* поездки. Пользователь без завершённой поездки не входит в retention cohort.
- **Cohort age N** — `date(activity) − date(first_completed_ride)` в полных календарных днях; age 0 — день активации.
- **Classical retention D<N>** — в числителе пользователь с ≥1 завершённой поездкой ровно на age N. Так, D30 не засчитывает поездку только на D29 или D31.
- **Rolling retention D<N>** — в числителе пользователь, у которого последняя наблюдаемая завершённая поездка случилась на age N или позже. Это приближённая survival-метрика «не исчез окончательно к N», а не активность в точке N.
- **Право попасть в знаменатель (eligibility)** — для D<N> включаем только cohort users, у которых `cohort_date + N <= data_end`. Иначе поздняя когорта искусственно выглядела бы churned. Знаменатель поэтому меняется с возрастом.

SQL и pandas используют одинаковые определения, но независимые реализации. Pipeline падает при их расхождении.

## Быстрый старт

Нужен Python 3.9+ и SQLite с поддержкой оконных функций (стандартный SQLite современных macOS/Linux подходит).

```bash
git clone https://github.com/Winlak/carsharing-retention-cohort-analysis.git
cd carsharing-retention-cohort-analysis
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
make reproduce
```

`make reproduce`:

1. генерирует synthetic `users` и `rides` из seed `20240801`;
2. запускает quality checks и загружает CSV в временную SQLite-базу;
3. выполняет SQL и pandas-анализ, сохраняет таблицы, графики и Markdown-отчёт;
4. строит versioned self-contained HTML handoff из валидированных агрегатов; локально также сохраняет пять Matplotlib SVG в `figures/`, но не версионирует их из-за различий font renderer между ОС;
5. исполняет ноутбук сверху вниз и канонизирует run-specific metadata: таблицы и текстовые outputs сохраняются, а inline-копии графиков убираются;
6. запускает линтер и тесты.

Полезные отдельные команды:

```bash
make all        # данные + SQL/pandas-анализ + отчёт
make notebook   # исполнить Jupyter-ноутбук
make check      # ruff + pytest
python scripts/run_pipeline.py --n-users 1200 --seed 7
```

Сгенерированные исходные CSV и SQLite-база игнорируются Git: репозиторий хранит генератор, код, SQL, компактные outputs и фигуры, а не большой датасет.

## Метод и выводы

- В [`sql/cohort_retention.sql`](sql/cohort_retention.sql) — классическая когортная матрица с recursive CTE, `CROSS JOIN` по возрастам, `LEFT JOIN` активности и age-specific denominator.
- В [`sql/rolling_retention.sql`](sql/rolling_retention.sql) — rolling retention через последнюю наблюдаемую поездку.
- В [`sql/retention_milestones.sql`](sql/retention_milestones.sql) — явный pivot D1/D7/D30.
- В [`sql/ride_frequency_and_gaps.sql`](sql/ride_frequency_and_gaps.sql) — частота и интервалы между поездками с `ROW_NUMBER()` и `LAG()`.
- В [`sql/early_experience_d30.sql`](sql/early_experience_d30.sql) — связь завершённых поездок на D1–D7 и статуса первой попытки с D30 без включения D30 в ранний признак.
- В pandas есть загрузка, фильтрация completed rides, `groupby`, `merge`, cohort calculations, heatmap, две retention/survival curves, сегментация и Wilson 95% CI.

Результат — **описательные ассоциации**, не causal inference. В синтетическом генераторе есть неэкспортируемая latent propensity; в реальном продукте её аналогами будут потребность в поездке, цена, доступность машин, маршрут и необнаруженные проблемы UX. Кроме того, анализ first-attempt status среди активированных пользователей подвержен selection/collider bias. Поэтому рекомендации из отчёта сформулированы как A/B-тесты, а не как обещание эффекта.

## Качество и воспроизводимость

CI в GitHub Actions выполняет `make reproduce` на чистом окружении, затем требует пустой `git diff` и проверяет точный состав generated-файлов, включая пять локальных SVG. В тестах проверяются:

- детерминированность генератора и базовые инварианты;
- корректные numerator/denominator для classical и rolling retention;
- right-censoring eligibility;
- отсутствие D30/data leakage в early-week exposure;
- совпадение SQL и pandas по матрицам retention.

## Лицензия

Код и искусственно сгенерированные материалы распространяются по [MIT License](LICENSE). Сгенерированные данные не являются открытым набором данных и не должны интерпретироваться как наблюдения реальной компании.
