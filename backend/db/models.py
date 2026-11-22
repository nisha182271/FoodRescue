"""SQLAlchemy 2.0 ORM models for FoodRescue."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('donor','receiver','admin')",
            name="ck_users_role",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    donor_profile: Mapped["DonorProfile | None"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    receiver_profile: Mapped["ReceiverProfile | None"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class DonorProfile(Base):
    __tablename__ = "donor_profiles"
    __table_args__ = (
        CheckConstraint(
            "business_type IN ('restaurant','caterer','venue','hostel','canteen')",
            name="ck_donor_profiles_business_type",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), primary_key=True
    )
    business_type: Mapped[str] = mapped_column(String(30), nullable=False)
    zone_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("zones.id"), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="donor_profile")
    zone: Mapped["Zone"] = relationship()


class ReceiverProfile(Base):
    __tablename__ = "receiver_profiles"
    __table_args__ = (
        CheckConstraint(
            "org_type IN ('ngo','kitchen','shelter','volunteer_group')",
            name="ck_receiver_profiles_org_type",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), primary_key=True
    )
    org_type: Mapped[str] = mapped_column(String(30), nullable=False)
    zone_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("zones.id"), nullable=False
    )
    daily_capacity_meals: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    accepts_categories: Mapped[list] = mapped_column(JSON, default=list)
    excluded_allergens: Mapped[list] = mapped_column(JSON, default=list)
    can_store_chilled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    search_radius_km: Mapped[float] = mapped_column(
        Float, default=10.0, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="receiver_profile")
    zone: Mapped["Zone"] = relationship()


class Donation(Base):
    __tablename__ = "donations"
    __table_args__ = (
        CheckConstraint("quantity_kg > 0", name="ck_donations_quantity_kg_positive"),
        CheckConstraint(
            "quantity_meals > 0", name="ck_donations_quantity_meals_positive"
        ),
        CheckConstraint(
            "storage_type IN ('ambient','chilled','hot','frozen')",
            name="ck_donations_storage_type",
        ),
        CheckConstraint(
            "status IN ('posted','claimed','collected','delivered','cancelled')",
            name="ck_donations_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    donor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    food_name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    quantity_kg: Mapped[float] = mapped_column(Float, nullable=False)
    quantity_meals: Mapped[int] = mapped_column(Integer, nullable=False)
    prepared_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    pickup_by: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    storage_type: Mapped[str] = mapped_column(String(20), nullable=False)
    zone_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("zones.id"), nullable=False
    )
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="posted", index=True
    )
    claimed_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    donor: Mapped["User"] = relationship(foreign_keys=[donor_id])
    claimed_by: Mapped["User | None"] = relationship(foreign_keys=[claimed_by_id])
    zone: Mapped["Zone"] = relationship()
    allergens: Mapped[list["DonationAllergen"]] = relationship(
        back_populates="donation",
        cascade="all, delete-orphan",
    )
    events: Mapped[list["StatusEvent"]] = relationship(
        back_populates="donation",
        order_by="StatusEvent.id",
        cascade="all, delete-orphan",
    )


class DonationAllergen(Base):
    __tablename__ = "donation_allergens"
    __table_args__ = (
        UniqueConstraint("donation_id", "allergen", name="uq_donation_allergen"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    donation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("donations.id"), nullable=False, index=True
    )
    allergen: Mapped[str] = mapped_column(String(40), nullable=False)

    donation: Mapped["Donation"] = relationship(back_populates="allergens")


class StatusEvent(Base):
    __tablename__ = "status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    donation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("donations.id"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    donation: Mapped["Donation"] = relationship(back_populates="events")


class FoodRequest(Base):
    __tablename__ = "food_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','withdrawn')",
            name="ck_food_requests_status",
        ),
        UniqueConstraint("donation_id", "receiver_id", name="uq_food_request"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    donation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("donations.id"), nullable=False, index=True
    )
    receiver_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    note: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
