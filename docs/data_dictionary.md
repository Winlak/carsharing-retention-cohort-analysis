# Data dictionary

Все поля ниже создаются локальным генератором. В данных нет PII, координат, адресов или реальных поездок.

## `users.csv`

| Поле | Тип | Гранулярность | Описание |
|---|---|---|---|
| `user_id` | string | registration | Синтетический стабильный идентификатор пользователя. |
| `registered_at` | UTC timestamp | registration | Дата регистрации в приложении. Не является cohort date. |
| `acquisition_channel` | category | registration | `organic`, `referral`, `paid_search`, `social`, `partners`. |
| `city` | category | registration | Синтетический город: Moscow, Saint_Petersburg, Kazan, Yekaterinburg. |
| `device_os` | category | registration | `ios` или `android`. |

## `rides.csv`

Одна строка — одна попытка бронирования, а не только успешная поездка.

| Поле | Тип | Обязательность | Описание |
|---|---|---|---|
| `ride_id` | string | всегда | Синтетический ключ попытки. |
| `user_id` | string | всегда | Foreign key к `users.user_id`. |
| `attempted_at` | UTC timestamp | всегда | Когда пользователь попытался начать бронирование. |
| `started_at` | UTC timestamp | только `completed` | Старт успешно начатой поездки. |
| `completed_at` | UTC timestamp | только `completed` | Завершение поездки; дата используется как event date в retention. |
| `status` | category | всегда | `completed`, `cancelled` или `error`. |
| `city` | category | всегда | Город попытки. |
| `vehicle_category` | category | всегда | `economy`, `comfort`, `electric`. |
| `booking_to_start_min` | integer | всегда | Минуты между попыткой и стартом/отказом. |
| `ride_duration_min` | float | только `completed` | Длительность завершённой поездки. |
| `distance_km` | float | только `completed` | Синтетический пробег. |
| `fare_rub` | float | только `completed` | Синтетическая цена. Не использовать как оценку рынка. |
| `cancellation_reason` | category/null | только `cancelled` | Причина отмены. |
| `error_code` | category/null | только `error` | Тип технической/платёжной ошибки. |

## Производные аналитические поля

| Поле | Определение |
|---|---|
| `cohort_date` | Минимальная `DATE(completed_at)` пользователя. |
| `cohort_week` | Понедельник недели `cohort_date`. |
| `cohort_age` | `DATE(completed_at) - cohort_date` в календарных днях. |
| `eligible_users` | Cohort users с `cohort_date + N <= data_end` для возраста N. |
| `retained_d30_classic` | Есть хотя бы одна completed ride ровно на age 30. |
| `rides_days_1_to_7` | Число completed rides в age 1–7; D0 и D30 не входят. |
| `first_attempt_status` | Статус самой ранней попытки пользователя по `attempted_at`. |
| `gap_days` | Разность с предыдущим `completed_at` пользователя; рассчитывается через `LAG()`. |

## Известные ограничения синтетической истории

Внутренняя latent propensity влияет и на вероятности повторной поездки, и на успех/повтор первой попытки, но намеренно не выгружается. Это делает учебную корреляцию реалистично некаузальной и защищает кейс от ложного causal wording.
