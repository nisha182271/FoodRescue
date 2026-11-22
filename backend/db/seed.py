"""Seed synthetic zones into the FoodRescue database.

Zones are generic placeholders (no real addresses). Seeding only happens when
the zones table is empty, so running it repeatedly is safe.

Usage (from the foodrescue-v2 directory):
    python -m backend.db.seed
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.models import Zone
from backend.db.session import SessionLocal, init_db

# (name, lat, lng) - approximate synthetic coordinates.
SYNTHETIC_ZONES: list[tuple[str, float, float]] = [
    ("Zone 1 Central", 12.9716, 77.5946),
    ("Zone 2 North", 13.0100, 77.5900),
    ("Zone 3 South", 12.9200, 77.6100),
    ("Zone 4 East", 12.9700, 77.6500),
    ("Zone 5 West", 12.9800, 77.5200),
    ("Zone 6 River", 12.9500, 77.5700),
]


def seed_zones(db: Session) -> int:
    """Insert the synthetic zones only if the zones table is empty.

    Adds rows to the session and flushes; the caller commits. Returns the number
    of zones inserted (0 if the table already had rows).
    """
    existing = db.scalar(select(func.count()).select_from(Zone))
    if existing:
        return 0
    for name, lat, lng in SYNTHETIC_ZONES:
        db.add(Zone(name=name, lat=lat, lng=lng))
    db.flush()
    return len(SYNTHETIC_ZONES)


if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        inserted = seed_zones(db)
        db.commit()
        print(f"Seeded {inserted} zone(s).")
    finally:
        db.close()
