"""Food-safety guidance helpers (pure functions, no database access).

Demo guidance only, not a food-safety certification. Datetimes are naive UTC.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.core.config import SAFETY_CAP_HOURS


def max_safe_hours(storage_type: str) -> int:
    """Return the maximum guidance hours before pickup for a storage type.

    Raises ValueError if the storage type is not in the safety table.
    """
    try:
        return SAFETY_CAP_HOURS[storage_type]
    except KeyError:
        raise ValueError(f"unknown storage type: {storage_type!r}") from None


def capped_pickup_by(
    prepared_at: datetime, donor_pickup_by: datetime, storage_type: str
) -> datetime:
    """Return the earlier of the donor's deadline and prepared_at plus the safety cap."""
    cap = prepared_at + timedelta(hours=max_safe_hours(storage_type))
    return min(donor_pickup_by, cap)


DISCLAIMER = (
    "Demo guidance only. This app does not certify food safety, and its time "
    "limits are informational values, not a food-safety certification. "
    "Follow your local food-safety rules and use your own judgement."
)

SAFETY_GUIDE = {
    "ambient": {
        "max_hours": SAFETY_CAP_HOURS["ambient"],
        "note": "Keep at room temperature; pick up within the demo window.",
    },
    "chilled": {
        "max_hours": SAFETY_CAP_HOURS["chilled"],
        "note": "Keep refrigerated; pick up within the demo window.",
    },
    "hot": {
        "max_hours": SAFETY_CAP_HOURS["hot"],
        "note": "Keep hot; pick up within the demo window.",
    },
    "frozen": {
        "max_hours": SAFETY_CAP_HOURS["frozen"],
        "note": "Keep frozen; pick up within the demo window.",
    },
}


def effective_pickup_by(
    prepared_at: datetime, donor_pickup_by: datetime, storage_type: str
) -> datetime:
    """Return the pickup deadline after applying the storage-type safety cap."""
    return capped_pickup_by(prepared_at, donor_pickup_by, storage_type)


def safety_window_error(
    prepared_at: datetime,
    pickup_by: datetime,
    storage_type: str,
    now: datetime,
) -> str | None:
    """Return an error message if the food window is invalid, else None."""
    if storage_type not in SAFETY_CAP_HOURS:
        return f"unknown storage type: {storage_type!r}"
    if prepared_at > now:
        return "prepared time cannot be in the future"
    if pickup_by <= now:
        return "pickup deadline has already passed"
    if pickup_by < prepared_at:
        return "pickup deadline cannot be before preparation time"
    return None

