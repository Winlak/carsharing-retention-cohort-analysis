"""Deterministic synthetic users and ride attempts for the portfolio case.

The generator deliberately creates both observed (city/channel) and unobserved
propensity differences.  It is useful for demonstrating why an association
between an early experience and retention is not automatically causal.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

DATA_START = pd.Timestamp("2024-01-01", tz="UTC")
DEFAULT_DATA_END = pd.Timestamp("2024-12-31 23:59:59", tz="UTC")


@dataclass(frozen=True)
class GenerationConfig:
    n_users: int = 6_000
    seed: int = 20240801
    data_end: pd.Timestamp = DEFAULT_DATA_END


CHANNELS = ("organic", "referral", "paid_search", "social", "partners")
CITIES = ("Moscow", "Saint_Petersburg", "Kazan", "Yekaterinburg")
DEVICES = ("ios", "android")

CHANNEL_WEIGHTS = np.array((0.29, 0.18, 0.25, 0.16, 0.12))
CITY_WEIGHTS = np.array((0.43, 0.24, 0.18, 0.15))
CHANNEL_EFFECT = {
    "organic": 0.17,
    "referral": 0.34,
    "paid_search": -0.06,
    "social": -0.20,
    "partners": 0.07,
}
CITY_EFFECT = {
    "Moscow": 0.15,
    "Saint_Petersburg": 0.05,
    "Kazan": -0.06,
    "Yekaterinburg": -0.11,
}
BASE_FARE = {
    "Moscow": 730.0,
    "Saint_Petersburg": 610.0,
    "Kazan": 510.0,
    "Yekaterinburg": 490.0,
}


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + np.exp(-value))


def _random_timestamp(
    date: pd.Timestamp, rng: np.random.Generator, minimum_hour: int = 7
) -> pd.Timestamp:
    """Return a UTC timestamp on the date with a plausible in-app booking hour."""
    minute_offset = int(rng.integers(minimum_hour * 60, 23 * 60 + 45))
    return date.normalize() + pd.Timedelta(minutes=minute_offset)


def _append_ride(
    rows: list[dict[str, object]],
    *,
    ride_id: int,
    user_id: str,
    city: str,
    attempted_at: pd.Timestamp,
    status: str,
    rng: np.random.Generator,
) -> None:
    """Append one ride attempt. Failed attempts intentionally have no ride facts."""
    vehicle = str(rng.choice(["economy", "comfort", "electric"], p=[0.55, 0.34, 0.11]))
    booking_to_start = int(np.clip(rng.gamma(2.0, 3.0), 1, 35))
    started_at: pd.Timestamp | pd.NaTType = pd.NaT
    completed_at: pd.Timestamp | pd.NaTType = pd.NaT
    duration: float | None = None
    distance: float | None = None
    fare: float | None = None
    cancellation_reason: str | None = None
    error_code: str | None = None

    if status == "completed":
        started_at = attempted_at + pd.Timedelta(minutes=booking_to_start)
        duration = float(np.clip(rng.lognormal(mean=3.15, sigma=0.43), 8, 150))
        completed_at = started_at + pd.Timedelta(minutes=duration)
        distance = round(float(duration * rng.uniform(0.34, 0.58)), 2)
        fare = round(BASE_FARE[city] * (duration / 42) * rng.uniform(0.78, 1.28), 2)
    elif status == "cancelled":
        cancellation_reason = str(
            rng.choice(
                ["user_cancelled", "price_changed", "vehicle_unavailable"], p=[0.50, 0.21, 0.29]
            )
        )
    else:
        error_code = str(
            rng.choice(["payment_declined", "app_timeout", "vehicle_unlock"], p=[0.35, 0.27, 0.38])
        )

    rows.append(
        {
            "ride_id": f"R{ride_id:08d}",
            "user_id": user_id,
            "attempted_at": attempted_at,
            "started_at": started_at,
            "completed_at": completed_at,
            "status": status,
            "city": city,
            "vehicle_category": vehicle,
            "booking_to_start_min": booking_to_start,
            "ride_duration_min": duration,
            "distance_km": distance,
            "fare_rub": fare,
            "cancellation_reason": cancellation_reason,
            "error_code": error_code,
        }
    )


def generate_synthetic_data(config: GenerationConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate users and ride attempts with fixed seed and no personal data.

    A retained user is not created by the analysis code: all outcomes emerge
    from the same simulation. The latent propensity is intentionally *not*
    persisted, mirroring an important unobserved-confounding limitation.
    """
    if config.n_users < 50:
        raise ValueError("n_users must be at least 50 for stable synthetic segments")
    if config.data_end <= DATA_START + pd.Timedelta(days=45):
        raise ValueError("data_end must leave at least 45 days after data start")

    rng = np.random.default_rng(config.seed)
    registration_latest = min(
        config.data_end - pd.Timedelta(days=8), pd.Timestamp("2024-11-15", tz="UTC")
    )
    registration_span = (registration_latest.normalize() - DATA_START.normalize()).days + 1
    user_ids = [f"U{i:07d}" for i in range(1, config.n_users + 1)]
    channels = rng.choice(CHANNELS, size=config.n_users, p=CHANNEL_WEIGHTS)
    cities = rng.choice(CITIES, size=config.n_users, p=CITY_WEIGHTS)
    devices = rng.choice(DEVICES, size=config.n_users, p=[0.48, 0.52])
    registration_days = rng.integers(0, registration_span, size=config.n_users)
    registered_at = DATA_START + pd.to_timedelta(registration_days, unit="D")

    user_rows: list[dict[str, object]] = []
    ride_rows: list[dict[str, object]] = []
    ride_id = 1

    for user_id, channel, city, device, registered in zip(
        user_ids, channels, cities, devices, registered_at
    ):
        # This individual-level propensity is deliberately unobserved downstream.
        latent_intent = float(rng.normal(0, 0.9))
        user_rows.append(
            {
                "user_id": user_id,
                "registered_at": registered,
                "acquisition_channel": channel,
                "city": city,
                "device_os": device,
            }
        )

        # Some registrations never try to book. They stay in the users table
        # but are not eligible for a first-completed-ride cohort.
        attempt_probability = _sigmoid(0.95 + 0.28 * latent_intent + CHANNEL_EFFECT[channel])
        if rng.random() > attempt_probability:
            continue

        first_day = registered + pd.Timedelta(days=int(rng.integers(0, 22)))
        if first_day > config.data_end:
            continue
        success_probability = _sigmoid(
            1.12 + 0.18 * latent_intent + CITY_EFFECT[city] + (0.10 if device == "ios" else 0.0)
        )
        first_status = (
            "completed"
            if rng.random() < success_probability
            else str(rng.choice(["cancelled", "error"], p=[0.68, 0.32]))
        )
        attempt_at = _random_timestamp(first_day, rng)
        _append_ride(
            ride_rows,
            ride_id=ride_id,
            user_id=user_id,
            city=city,
            attempted_at=attempt_at,
            status=first_status,
            rng=rng,
        )
        ride_id += 1

        first_completed_at: pd.Timestamp | None = None
        first_attempt_failed = first_status != "completed"
        if first_status == "completed":
            first_completed_at = ride_rows[-1]["completed_at"]  # type: ignore[assignment]
        else:
            # A failed first attempt makes reactivation less likely, while latent
            # intent still affects both retry and future rides: intentional confounding.
            retry_probability = _sigmoid(
                -0.08 + 0.80 * latent_intent + 0.12 * CHANNEL_EFFECT[channel]
            )
            if rng.random() < retry_probability:
                retry_day = first_day + pd.Timedelta(days=int(rng.integers(1, 10)))
                if retry_day <= config.data_end:
                    retry_success = _sigmoid(1.00 + 0.22 * latent_intent + CITY_EFFECT[city])
                    retry_status = (
                        "completed"
                        if rng.random() < retry_success
                        else str(rng.choice(["cancelled", "error"], p=[0.65, 0.35]))
                    )
                    retry_at = _random_timestamp(retry_day, rng)
                    _append_ride(
                        ride_rows,
                        ride_id=ride_id,
                        user_id=user_id,
                        city=city,
                        attempted_at=retry_at,
                        status=retry_status,
                        rng=rng,
                    )
                    ride_id += 1
                    if retry_status == "completed":
                        first_completed_at = ride_rows[-1]["completed_at"]  # type: ignore[assignment]

        if first_completed_at is None:
            continue

        cohort_day = pd.Timestamp(first_completed_at).normalize()
        max_age = min(120, (config.data_end.normalize() - cohort_day).days)
        experience_penalty = 0.36 if first_attempt_failed else 0.0
        # A latent survival process creates a finite active lifetime. Daily
        # activity then declines with age within that lifetime. Both processes
        # share intent and early-friction inputs, deliberately inducing an
        # observational association between early behaviour and D30.
        daily_survival = _sigmoid(
            3.75
            + 0.28 * latent_intent
            + 0.14 * CHANNEL_EFFECT[channel]
            + 0.12 * CITY_EFFECT[city]
            - experience_penalty
        )
        for age in range(1, max_age + 1):
            if rng.random() > daily_survival:
                break
            daily_logit = (
                -1.88
                + 0.86 * latent_intent
                + CHANNEL_EFFECT[channel]
                + CITY_EFFECT[city]
                - experience_penalty
                - 0.018 * age
                + (0.22 if age <= 7 else 0.0)
            )
            if rng.random() >= _sigmoid(daily_logit):
                continue
            rides_today = 1 + int(rng.random() < 0.055 + 0.025 * max(latent_intent, 0))
            for _ in range(rides_today):
                activity_day = cohort_day + pd.Timedelta(days=age)
                completed_at = _random_timestamp(activity_day, rng)
                _append_ride(
                    ride_rows,
                    ride_id=ride_id,
                    user_id=user_id,
                    city=city,
                    attempted_at=completed_at - pd.Timedelta(minutes=int(rng.integers(1, 12))),
                    status="completed",
                    rng=rng,
                )
                ride_id += 1

    users = pd.DataFrame(user_rows).sort_values("user_id").reset_index(drop=True)
    rides = pd.DataFrame(ride_rows).sort_values(["attempted_at", "ride_id"]).reset_index(drop=True)
    for column in ("attempted_at", "started_at", "completed_at"):
        rides[column] = pd.to_datetime(rides[column], utc=True)
    # A booking can start late on the final day and finish after the extract's
    # cut-off. Such a completion is not observable in this snapshot, so remove
    # the whole attempt rather than leaking a future activity into a cohort.
    rides = rides.loc[
        rides["completed_at"].isna() | rides["completed_at"].le(config.data_end)
    ].copy()
    rides = rides.sort_values(["attempted_at", "ride_id"]).reset_index(drop=True)
    users["registered_at"] = pd.to_datetime(users["registered_at"], utc=True)
    return users, rides


def write_synthetic_data(output_dir: Path, config: GenerationConfig) -> tuple[Path, Path]:
    """Materialize reproducible CSV inputs and a small JSON metadata file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    users, rides = generate_synthetic_data(config)
    users_path = output_dir / "users.csv"
    rides_path = output_dir / "rides.csv"
    users.to_csv(users_path, index=False)
    rides.to_csv(rides_path, index=False)
    metadata = pd.DataFrame(
        [
            {
                "synthetic": True,
                "seed": config.seed,
                "n_users_requested": config.n_users,
                "data_end_utc": config.data_end.isoformat(),
                "users_written": len(users),
                "ride_attempts_written": len(rides),
            }
        ]
    )
    metadata.to_json(output_dir / "metadata.json", orient="records", indent=2)
    return users_path, rides_path


def completed_rides(rides: pd.DataFrame) -> pd.DataFrame:
    """Return completed rides only, the behavioural event used in retention."""
    return rides.loc[rides["status"].eq("completed")].copy()


def ensure_columns(frame: pd.DataFrame, expected: Iterable[str], name: str) -> None:
    missing = set(expected).difference(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing required columns: {sorted(missing)}")
