-- Когортная матрица классического retention по дням жизни когорты.
-- `analysis_parameters` создаётся pipeline; data_end_date — последняя полностью
-- наблюдаемая календарная дата. Каждый знаменатель строится только из пользователей,
-- для которых cohort_date + cohort_age уже наступил.
WITH RECURSIVE ages(cohort_age) AS (
    SELECT 0
    UNION ALL
    SELECT cohort_age + 1 FROM ages WHERE cohort_age < 60
),
completed_rides AS (
    SELECT user_id, DATE(completed_at) AS ride_date
    FROM rides
    WHERE status = 'completed'
),
first_completed_ride AS (
    SELECT user_id, MIN(ride_date) AS cohort_date
    FROM completed_rides
    GROUP BY user_id
),
cohort_users AS (
    SELECT
        f.user_id,
        f.cohort_date,
        DATE(f.cohort_date, '-' || ((CAST(STRFTIME('%w', f.cohort_date) AS INTEGER) + 6) % 7) || ' days')
            AS cohort_week
    FROM first_completed_ride AS f
),
activity_days AS (
    SELECT DISTINCT user_id, ride_date
    FROM completed_rides
),
eligible_users AS (
    SELECT c.user_id, c.cohort_week, c.cohort_date, a.cohort_age
    FROM cohort_users AS c
    CROSS JOIN ages AS a
    CROSS JOIN analysis_parameters AS p
    WHERE DATE(c.cohort_date, '+' || a.cohort_age || ' days') <= p.data_end_date
),
retention_at_age AS (
    SELECT
        e.cohort_week,
        e.cohort_age,
        e.user_id,
        CASE WHEN d.user_id IS NOT NULL THEN 1 ELSE 0 END AS retained_classic
    FROM eligible_users AS e
    LEFT JOIN activity_days AS d
        ON d.user_id = e.user_id
       AND d.ride_date = DATE(e.cohort_date, '+' || e.cohort_age || ' days')
)
SELECT
    cohort_week,
    cohort_age,
    COUNT(*) AS eligible_users,
    SUM(retained_classic) AS retained_users,
    ROUND(1.0 * SUM(retained_classic) / COUNT(*), 6) AS classical_retention
FROM retention_at_age
GROUP BY cohort_week, cohort_age
ORDER BY cohort_week, cohort_age;
