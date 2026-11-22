"""Impact aggregates (pure functions, no database access).

Only donations with status 'delivered' count. Waste avoided equals diverted kg
(PLAN.md section 7 assumption).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

# Assumption for demonstration figures: 1 kg of food is about 2 meals.
# Defined in backend/core/config.py; re-exported here for convenience.
from backend.core.config import MEALS_PER_KG  # noqa: F401


def impact_totals(donations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Sum meals, kg and counts over delivered donations."""
    delivered = [d for d in donations if d.get("status") == "delivered"]
    meals_saved = sum(d["quantity_meals"] for d in delivered)
    kg_diverted = round(sum(float(d["quantity_kg"]) for d in delivered), 2)
    return {
        "meals_saved": meals_saved,
        "kg_diverted": kg_diverted,
        "waste_avoided_kg": kg_diverted,
        "counts": {"delivered": len(delivered)},
    }
