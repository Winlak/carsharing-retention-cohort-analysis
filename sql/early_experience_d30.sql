-- Связь первых 7 дней и статуса первой попытки с классическим D30.
-- Считаем только активированных пользователей, у которых D30 уже наблюдаем.
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
ranked_attempts AS (
    SELECT
        r.user_id,
        r.status,
        r.attempted_at,
        ROW_NUMBER() OVER (PARTITION BY r.user_id ORDER BY r.attempted_at, r.ride_id) AS attempt_number
    FROM rides AS r
),
first_attempt AS (
    SELECT user_id, status AS first_attempt_status
    FROM ranked_attempts
    WHERE attempt_number = 1
),
eligible_cohorts AS (
    SELECT f.user_id, f.cohort_date
    FROM first_completed_ride AS f
    CROSS JOIN analysis_parameters AS p
    WHERE DATE(f.cohort_date, '+30 days') <= p.data_end_date
),
user_outcomes AS (
    SELECT
        e.user_id,
        e.cohort_date,
        u.acquisition_channel,
        u.city,
        f.first_attempt_status,
        SUM(CASE WHEN c.ride_date > e.cohort_date
                      AND c.ride_date <= DATE(e.cohort_date, '+7 days') THEN 1 ELSE 0 END) AS rides_days_1_to_7,
        MAX(CASE WHEN c.ride_date = DATE(e.cohort_date, '+30 days') THEN 1 ELSE 0 END) AS retained_d30_classic
    FROM eligible_cohorts AS e
    INNER JOIN users AS u ON u.user_id = e.user_id
    INNER JOIN first_attempt AS f ON f.user_id = e.user_id
    LEFT JOIN completed_rides AS c ON c.user_id = e.user_id
    GROUP BY e.user_id, e.cohort_date, u.acquisition_channel, u.city, f.first_attempt_status
)
SELECT *
FROM user_outcomes
ORDER BY user_id;
