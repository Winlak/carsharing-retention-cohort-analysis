-- Rolling retention: пользователь вернулся хотя бы раз в день N или позже
-- до конца доступного окна наблюдения. Это не "retention в точке N";
-- он равен доле пользователей с last_active_age >= N.
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
last_completed_ride AS (
    SELECT user_id, MAX(ride_date) AS last_ride_date
    FROM completed_rides
    GROUP BY user_id
),
cohort_users AS (
    SELECT
        f.user_id,
        f.cohort_date,
        l.last_ride_date,
        DATE(f.cohort_date, '-' || ((CAST(STRFTIME('%w', f.cohort_date) AS INTEGER) + 6) % 7) || ' days')
            AS cohort_week
    FROM first_completed_ride AS f
    INNER JOIN last_completed_ride AS l ON l.user_id = f.user_id
),
eligible_users AS (
    SELECT c.user_id, c.cohort_week, c.cohort_date, c.last_ride_date, a.cohort_age
    FROM cohort_users AS c
    CROSS JOIN ages AS a
    CROSS JOIN analysis_parameters AS p
    WHERE DATE(c.cohort_date, '+' || a.cohort_age || ' days') <= p.data_end_date
)
SELECT
    cohort_week,
    cohort_age,
    COUNT(*) AS eligible_users,
    SUM(CASE WHEN last_ride_date >= DATE(cohort_date, '+' || cohort_age || ' days') THEN 1 ELSE 0 END)
        AS retained_users,
    ROUND(
        1.0 * SUM(CASE WHEN last_ride_date >= DATE(cohort_date, '+' || cohort_age || ' days') THEN 1 ELSE 0 END)
        / COUNT(*),
        6
    ) AS rolling_retention
FROM eligible_users
GROUP BY cohort_week, cohort_age
ORDER BY cohort_week, cohort_age;
