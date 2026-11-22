"""FoodRescue FastAPI application (PLAN.md section 4)."""

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.core.deps import get_current_user, require_roles
from backend.core.security import create_token, hash_password, verify_password
from backend.db.models import (
    Donation,
    DonationAllergen,
    DonorProfile,
    ReceiverProfile,
    StatusEvent,
    User,
    Zone,
    utcnow,
)
from backend.db.seed import seed_zones
from backend.db.session import SessionLocal, get_db, init_db
from backend.schemas import DonationIn, DonationOut, LoginIn, RegisterIn, StatusIn, TokenOut, to_utc_naive
from backend.services.impact import impact_totals
from backend.services.matching import rank_donations
from backend.services.pickup_state import transition
from backend.services.safety import (
    DISCLAIMER,
    SAFETY_GUIDE,
    effective_pickup_by,
    safety_window_error,
)

app = FastAPI(title="FoodRescue")


@app.on_event("startup")
def _startup() -> None:
    init_db()
    with SessionLocal() as db:
        seed_zones(db)  # no-op unless the zones table is empty
        db.commit()


# ---------- helpers ----------

def _donation_out(d: Donation) -> dict:
    return {
        "id": d.id,
        "donor_id": d.donor_id,
        "donor_name": d.donor.name,
        "food_name": d.food_name,
        "category": d.category,
        "quantity_kg": d.quantity_kg,
        "quantity_meals": d.quantity_meals,
        "prepared_at": d.prepared_at,
        "pickup_by": d.pickup_by,
        "storage_type": d.storage_type,
        "zone_id": d.zone_id,
        "zone_name": d.zone.name,
        "status": d.status,
        "allergens": sorted(a.allergen for a in d.allergens),
        "notes": None,  # Donation model has no notes column
        "claimed_by_id": d.claimed_by_id,
        "claimed_by_name": d.claimed_by.name if d.claimed_by else None,
        "created_at": d.created_at,
    }


def _match_dict(d: Donation) -> dict:
    return {
        "id": d.id,
        "meals": d.quantity_meals,
        "lat": d.lat,
        "lng": d.lng,
        "pickup_by": d.pickup_by,
        "prepared_at": d.prepared_at,
        "storage_type": d.storage_type,
        "category": d.category,
        "allergens": [a.allergen for a in d.allergens],
        "status": d.status,
    }


def _receiver_dict(user: User) -> dict:
    profile = user.receiver_profile
    if profile is None:
        raise HTTPException(status_code=403, detail="Not a receiver account")
    return {
        "lat": profile.zone.lat,
        "lng": profile.zone.lng,
        "radius_km": profile.search_radius_km,
        "capacity_meals": profile.daily_capacity_meals,
        "accepts_categories": profile.accepts_categories or [],
        "excluded_allergens": profile.excluded_allergens or [],
        "can_store_chilled": profile.can_store_chilled,
    }


def _get_donation_or_404(db: Session, donation_id: int) -> Donation:
    donation = db.get(Donation, donation_id)
    if donation is None:
        raise HTTPException(status_code=404, detail="Donation not found")
    return donation


# ---------- health and identity ----------

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/me")
def me(user: User = Depends(get_current_user)) -> dict:
    profile = None
    zone_id = None
    if user.donor_profile is not None:
        p = user.donor_profile
        profile = {"business_type": p.business_type, "zone_id": p.zone_id}
        zone_id = p.zone_id
    elif user.receiver_profile is not None:
        r = user.receiver_profile
        profile = {
            "org_type": r.org_type,
            "zone_id": r.zone_id,
            "daily_capacity_meals": r.daily_capacity_meals,
            "accepts_categories": r.accepts_categories or [],
            "excluded_allergens": r.excluded_allergens or [],
            "can_store_chilled": r.can_store_chilled,
            "search_radius_km": r.search_radius_km,
        }
        zone_id = r.zone_id
    return {"id": user.id, "name": user.name, "role": user.role, "zone_id": zone_id, "profile": profile}


@app.post("/api/auth/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> dict:
    if db.scalars(select(User).where(User.name == body.name)).first() is not None:
        raise HTTPException(status_code=409, detail="Name already registered")
    # Defaults when omitted: zone = first zone by id, donor business_type = "restaurant",
    # receiver org_type = "ngo".
    zone_id = body.zone_id
    if zone_id is None:
        first_zone = db.scalars(select(Zone).order_by(Zone.id)).first()
        if first_zone is None:
            raise HTTPException(status_code=500, detail="Run seed first")
        zone_id = first_zone.id
    if db.get(Zone, zone_id) is None:
        raise HTTPException(status_code=422, detail="Unknown zone")
    user = User(
        role=body.role,
        name=body.name,
        password_hash=hash_password(body.password),
    )
    if body.role == "donor":
        user.donor_profile = DonorProfile(
            business_type=body.business_type or "restaurant",
            zone_id=zone_id,
        )
    else:
        user.receiver_profile = ReceiverProfile(
            org_type=body.org_type or "ngo",
            zone_id=zone_id,
            daily_capacity_meals=body.daily_capacity_meals,
            accepts_categories=body.accepts_categories,
            excluded_allergens=body.excluded_allergens,
            can_store_chilled=body.can_store_chilled,
            search_radius_km=body.search_radius_km,
        )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"access_token": create_token(user.id, user.role), "user": me(user)}


@app.post("/api/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> dict:
    user = db.scalars(select(User).where(User.name == body.name)).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid name or password")
    return {"access_token": create_token(user.id, user.role), "user": me(user)}


# ---------- meta ----------

@app.get("/api/meta/zones")
def zones(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Zone).order_by(Zone.name)).all()
    return [{"id": z.id, "name": z.name, "lat": z.lat, "lng": z.lng} for z in rows]


@app.get("/api/meta/safety")
def safety_meta() -> dict:
    return {"storage_types": SAFETY_GUIDE, "disclaimer": DISCLAIMER}


# ---------- donations ----------

@app.post("/api/donations", response_model=DonationOut, status_code=201)
def create_donation(
    body: DonationIn,
    user: User = Depends(require_roles("donor")),
    db: Session = Depends(get_db),
) -> dict:
    zone = db.get(Zone, body.zone_id)
    if zone is None:
        raise HTTPException(status_code=422, detail="Unknown zone")
    now = utcnow()
    prepared_at = to_utc_naive(body.prepared_at)
    donor_pickup_by = to_utc_naive(body.pickup_by)
    error = safety_window_error(prepared_at, donor_pickup_by, body.storage_type, now)
    if error is not None:
        raise HTTPException(status_code=422, detail=error)
    donation = Donation(
        donor_id=user.id,
        food_name=body.food_name,
        category=body.category,
        quantity_kg=body.quantity_kg,
        quantity_meals=body.quantity_meals,
        prepared_at=prepared_at,
        pickup_by=effective_pickup_by(prepared_at, donor_pickup_by, body.storage_type),
        storage_type=body.storage_type,
        zone_id=zone.id,
        lat=zone.lat,
        lng=zone.lng,
        status="posted",
        created_at=now,
    )
    donation.allergens = [
        DonationAllergen(allergen=a) for a in dict.fromkeys(body.allergens)
    ]
    db.add(donation)
    db.commit()
    db.refresh(donation)
    return _donation_out(donation)


@app.get("/api/donations", response_model=list[DonationOut])
def list_donations(
    zone_id: int | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(Donation).where(Donation.status == "posted")
    if zone_id is not None:
        stmt = stmt.where(Donation.zone_id == zone_id)
    if category is not None:
        stmt = stmt.where(Donation.category == category)
    rows = db.scalars(stmt.order_by(Donation.pickup_by)).all()
    return [_donation_out(d) for d in rows]


@app.get("/api/donations/mine", response_model=list[DonationOut])
def my_donations(
    user: User = Depends(require_roles("donor")),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(
        select(Donation)
        .where(Donation.donor_id == user.id)
        .order_by(Donation.created_at.desc())
    ).all()
    return [_donation_out(d) for d in rows]


@app.get("/api/donations/{donation_id}", response_model=DonationOut)
def get_donation(donation_id: int, db: Session = Depends(get_db)) -> dict:
    return _donation_out(_get_donation_or_404(db, donation_id))


@app.get("/api/matches")
def matches(
    user: User = Depends(require_roles("receiver")),
    db: Session = Depends(get_db),
) -> list[dict]:
    receiver = _receiver_dict(user)
    rows = db.scalars(select(Donation).where(Donation.status == "posted")).all()
    ranked = rank_donations([_match_dict(d) for d in rows], receiver, utcnow())
    by_id = {d.id: d for d in rows}
    return [{**r, "donation": _donation_out(by_id[r["id"]])} for r in ranked]


@app.post("/api/donations/{donation_id}/claim", response_model=DonationOut)
def claim_donation(
    donation_id: int,
    user: User = Depends(require_roles("receiver")),
    db: Session = Depends(get_db),
) -> dict:
    _get_donation_or_404(db, donation_id)
    now = utcnow()
    result = db.execute(
        update(Donation)
        .where(Donation.id == donation_id, Donation.status == "posted")
        .values(status="claimed", claimed_by_id=user.id, claimed_at=now)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Donation is no longer available")
    db.add(
        StatusEvent(
            donation_id=donation_id,
            from_status="posted",
            to_status="claimed",
            actor_id=user.id,
            at=now,
        )
    )
    db.commit()
    donation = _get_donation_or_404(db, donation_id)
    db.refresh(donation)
    return _donation_out(donation)


@app.post("/api/donations/{donation_id}/status", response_model=DonationOut)
def update_status(
    donation_id: int,
    body: StatusIn,
    user: User = Depends(require_roles("receiver")),
    db: Session = Depends(get_db),
) -> dict:
    donation = _get_donation_or_404(db, donation_id)
    if donation.claimed_by_id != user.id:
        raise HTTPException(status_code=403, detail="Only the claimant can update this donation")
    try:
        transition(db, donation, body.to_status, user.id, utcnow())
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    db.refresh(donation)
    return _donation_out(donation)


@app.get("/api/donations/{donation_id}/events")
def donation_events(
    donation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    donation = _get_donation_or_404(db, donation_id)
    if user.id not in (donation.donor_id, donation.claimed_by_id):
        raise HTTPException(status_code=403, detail="Not allowed to view this timeline")
    return [
        {
            "id": e.id,
            "from_status": e.from_status,
            "to_status": e.to_status,
            "actor_id": e.actor_id,
            "at": e.at,
        }
        for e in donation.events
    ]


# ---------- impact ----------

@app.get("/api/impact")
def impact(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(Donation).where(Donation.status == "delivered")).all()
    return impact_totals(
        [
            {
                "status": d.status,
                "quantity_meals": d.quantity_meals,
                "quantity_kg": d.quantity_kg,
            }
            for d in rows
        ]
    )


# ---------- frontend (must stay last so /api routes take precedence) ----------

app.mount(
    "/",
    StaticFiles(
        directory=Path(__file__).resolve().parent.parent / "frontend",
        html=True,
    ),
    name="frontend",
)
