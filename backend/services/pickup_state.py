"""Pickup lifecycle state machine for donations.

Functions here mutate ORM objects but never commit; the caller owns the
transaction. ``StatusEvent`` is linked through the ``donation`` relationship,
so no flush is needed before the event is created.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from backend.db.models import Donation, StatusEvent

ALLOWED: dict[str, set[str]] = {
    "posted": {"claimed", "cancelled"},
    "claimed": {"collected", "cancelled"},
    "collected": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in ALLOWED.get(from_status, set())


def transition(
    db: Session,
    donation: Donation,
    to_status: str,
    actor_id: int | None,
    now: datetime,
) -> None:
    if not can_transition(donation.status, to_status):
        raise ValueError(f"Cannot move from {donation.status} to {to_status}")

    from_status = donation.status
    donation.status = to_status

    if to_status == "claimed":
        donation.claimed_at = now
    elif to_status == "collected":
        donation.collected_at = now
    elif to_status == "delivered":
        donation.delivered_at = now

    # Use the relationship rather than donation_id so this works before flush.
    db.add(
        StatusEvent(
            donation=donation,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor_id,
            at=now,
        )
    )
