-- Частота и интервалы: оконные функции дают номер завершённой поездки и
-- время с предыдущей. Одна строка = одна завершённая поездка пользователя.
WITH completed_rides AS (
    SELECT
        r.ride_id,
        r.user_id,
        r.completed_at,
        DATE(r.completed_at) AS ride_date,
        r.city,
        r.fare_rub
    FROM rides AS r
    WHERE r.status = 'completed'
),
first_completed_ride AS (
    SELECT user_id, MIN(ride_date) AS cohort_date
    FROM completed_rides
    GROUP BY user_id
),
ordered_rides AS (
    SELECT
        c.ride_id,
        c.user_id,
        c.completed_at,
        c.ride_date,
        c.city,
        c.fare_rub,
        f.cohort_date,
        CAST(JULIANDAY(c.ride_date) - JULIANDAY(f.cohort_date) AS INTEGER) AS cohort_age,
        ROW_NUMBER() OVER (PARTITION BY c.user_id ORDER BY c.completed_at, c.ride_id) AS completed_ride_number,
        LAG(c.completed_at) OVER (PARTITION BY c.user_id ORDER BY c.completed_at, c.ride_id) AS previous_completed_at
    FROM completed_rides AS c
    INNER JOIN first_completed_ride AS f ON f.user_id = c.user_id
)
SELECT
    o.*,
    ROUND(JULIANDAY(o.completed_at) - JULIANDAY(o.previous_completed_at), 4) AS gap_days,
    u.acquisition_channel,
    u.device_os
FROM ordered_rides AS o
INNER JOIN users AS u ON u.user_id = o.user_id
ORDER BY o.user_id, o.completed_ride_number;
