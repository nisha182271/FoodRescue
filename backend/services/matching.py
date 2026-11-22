"""Smart matching (PLAN.md section 5). Pure functions, no database access.

Donations and receivers are plain dicts:
- donation: id, meals, lat, lng, pickup_by, prepared_at, storage_type,
  category, allergens (list), and optionally status (default "posted").
- receiver: lat, lng, radius_km, capacity_meals, accepts_categories (list,
  empty means accepts all), excluded_allergens (list), can_store_chilled.

All datetimes are naive UTC.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from backend.core.config import AVERAGE_SPEED_KMH, MATCH_BUFFER_MINUTES, MATCH_WEIGHTS
from backend.core.geo import haversine_km

# Urgency reaches full points at zero remaining window and zero at this horizon.
# Remaining window = hours until pickup_by, minus travel time and the buffer.
URGENCY_HORIZON_HOURS = 6.0

# Need-match points: 15 when the category is explicitly listed (preferred).
# A receiver that accepts all categories (empty list) gets 12, per the test
# suite's expectations.
NEED_PREFERRED_PTS = 15.0
NEED_ACCEPT_ALL_PTS = 12.0


def _hard_filter_reason(
    donation: Mapping[str, Any],
    receiver: Mapping[str, Any],
    distance_km: float,
    travel_h: float,
    now: datetime,
) -> str | None:
    """Return the reason the donation is excluded, or None if it passes."""
    if donation.get("status", "posted") != "posted":
        return "not posted"
    if distance_km > receiver["radius_km"]:
        return "outside search radius"
    if set(donation.get("allergens", [])) & set(receiver.get("excluded_allergens", [])):
        return "contains an excluded allergen"
    accepts = receiver.get("accepts_categories") or []
    if accepts and donation["category"] not in accepts:
        return "category not accepted"
    if donation["storage_type"] == "chilled" and not receiver.get("can_store_chilled"):
        return "receiver cannot store chilled food"
    hours_left = (donation["pickup_by"] - now).total_seconds() / 3600.0
    buffer_h = MATCH_BUFFER_MINUTES / 60.0
    if hours_left - travel_h - buffer_h < 0:
        return "pickup window too short"
    return None


def score_donation(
    donation: Mapping[str, Any], receiver: Mapping[str, Any], now: datetime
) -> dict[str, Any]:
    """Apply hard filters, then score a donation for a receiver.

    Returns a dict with id, eligible, reason, score (0-100, rounded to 2 dp)
    and breakdown (distance, quantity, urgency, need points).
    """
    result: dict[str, Any] = {
        "id": donation.get("id"),
        "eligible": False,
        "reason": None,
        "score": 0.0,
        "breakdown": {},
    }
    distance = haversine_km(
        donation["lat"], donation["lng"], receiver["lat"], receiver["lng"]
    )
    travel_h = distance / AVERAGE_SPEED_KMH
    reason = _hard_filter_reason(donation, receiver, distance, travel_h, now)
    if reason is not None:
        result["reason"] = reason
        return result

    w = MATCH_WEIGHTS

    # Distance: closer is better, zero points at the radius edge.
    radius = receiver["radius_km"]
    distance_pts = w["distance"] * max(0.0, 1.0 - distance / radius) if radius > 0 else 0.0

    # Quantity fit: ratio of the smaller to the larger of meals and daily need.
    meals = donation["meals"]
    need = receiver["capacity_meals"]
    larger = max(meals, need)
    quantity_pts = w["quantity"] * min(meals, need) / larger if larger > 0 else 0.0

    # Urgency: remaining feasible window (hours until pickup_by minus travel
    # time and buffer). Shorter window -> more points, linear over the horizon.
    hours_left = (donation["pickup_by"] - now).total_seconds() / 3600.0
    remaining_h = hours_left - travel_h - MATCH_BUFFER_MINUTES / 60.0
    urgency_frac = 1.0 - remaining_h / URGENCY_HORIZON_HOURS
    urgency_pts = w["urgency"] * min(1.0, max(0.0, urgency_frac))

    # Need match: explicitly preferred category vs. accept-all receiver.
    accepts = receiver.get("accepts_categories") or []
    need_pts = NEED_PREFERRED_PTS if donation["category"] in accepts else NEED_ACCEPT_ALL_PTS

    breakdown = {
        "distance": round(distance_pts, 2),
        "quantity": round(quantity_pts, 2),
        "urgency": round(urgency_pts, 2),
        "need": round(need_pts, 2),
    }
    result["eligible"] = True
    result["breakdown"] = breakdown
    result["score"] = round(min(100.0, sum(breakdown.values())), 2)
    return result


def rank_donations(
    donations: list[Mapping[str, Any]], receiver: Mapping[str, Any], now: datetime
) -> list[dict[str, Any]]:
    """Return eligible results sorted by score desc, then earlier pickup_by."""
    pairs = []
    for donation in donations:
        result = score_donation(donation, receiver, now)
        if result["eligible"]:
            pairs.append((donation["pickup_by"], result))
    pairs.sort(key=lambda p: (-p[1]["score"], p[0]))
    return [result for _, result in pairs]
