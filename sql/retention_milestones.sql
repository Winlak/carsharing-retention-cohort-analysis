-- D1/D7/D30 для каждой недельной когорты: два определения рядом.
WITH completed_rides AS (
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
activity_days AS (
    SELECT DISTINCT user_id, ride_date
    FROM completed_rides
),
milestone_rows AS (
    SELECT
        c.cohort_week,
        c.user_id,
        milestone.day_number,
        CASE WHEN a.user_id IS NOT NULL THEN 1 ELSE 0 END AS classic_retained,
        CASE WHEN c.last_ride_date >= DATE(c.cohort_date, '+' || milestone.day_number || ' days') THEN 1 ELSE 0 END
            AS rolling_retained
    FROM cohort_users AS c
    CROSS JOIN (SELECT 1 AS day_number UNION ALL SELECT 7 UNION ALL SELECT 30) AS milestone
    CROSS JOIN analysis_parameters AS p
    LEFT JOIN activity_days AS a
        ON a.user_id = c.user_id
       AND a.ride_date = DATE(c.cohort_date, '+' || milestone.day_number || ' days')
    WHERE DATE(c.cohort_date, '+' || milestone.day_number || ' days') <= p.data_end_date
)
SELECT
    cohort_week,
    COUNT(DISTINCT CASE WHEN day_number = 1 THEN user_id END) AS eligible_d1,
    ROUND(1.0 * SUM(CASE WHEN day_number = 1 THEN classic_retained END)
        / COUNT(DISTINCT CASE WHEN day_number = 1 THEN user_id END), 6) AS classic_d1,
    ROUND(1.0 * SUM(CASE WHEN day_number = 1 THEN rolling_retained END)
        / COUNT(DISTINCT CASE WHEN day_number = 1 THEN user_id END), 6) AS rolling_d1,
    COUNT(DISTINCT CASE WHEN day_number = 7 THEN user_id END) AS eligible_d7,
    ROUND(1.0 * SUM(CASE WHEN day_number = 7 THEN classic_retained END)
        / COUNT(DISTINCT CASE WHEN day_number = 7 THEN user_id END), 6) AS classic_d7,
    ROUND(1.0 * SUM(CASE WHEN day_number = 7 THEN rolling_retained END)
        / COUNT(DISTINCT CASE WHEN day_number = 7 THEN user_id END), 6) AS rolling_d7,
    COUNT(DISTINCT CASE WHEN day_number = 30 THEN user_id END) AS eligible_d30,
    ROUND(1.0 * SUM(CASE WHEN day_number = 30 THEN classic_retained END)
        / COUNT(DISTINCT CASE WHEN day_number = 30 THEN user_id END), 6) AS classic_d30,
    ROUND(1.0 * SUM(CASE WHEN day_number = 30 THEN rolling_retained END)
        / COUNT(DISTINCT CASE WHEN day_number = 30 THEN user_id END), 6) AS rolling_d30
FROM milestone_rows
GROUP BY cohort_week
ORDER BY cohort_week;
