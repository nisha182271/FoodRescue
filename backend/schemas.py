"""Pydantic v2 request/response schemas for FoodRescue."""

from __future__ import annotations

import re  # noqa: F401  (reserved for future pattern helpers)
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

# Display name: trimmed, 1-120 characters, no character-set restriction.
Username = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
Password = Annotated[str, Field(min_length=8, max_length=128)]


def to_utc_naive(dt: datetime) -> datetime:
    """Normalise a datetime to naive UTC (the storage convention used by models)."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class RegisterIn(BaseModel):
    name: Username
    password: Password
    role: Literal["donor", "receiver"]
    # Optional: the register route fills defaults (see main.py) when omitted.
    zone_id: int | None = None
    business_type: Literal["restaurant", "caterer", "venue", "hostel", "canteen"] | None = None
    org_type: Literal["ngo", "kitchen", "shelter", "volunteer_group"] | None = None
    daily_capacity_meals: int = Field(default=0, ge=0)
    accepts_categories: list[str] = []
    excluded_allergens: list[str] = []
    can_store_chilled: bool = False
    search_radius_km: float = Field(default=10.0, gt=0, le=100)


class LoginIn(BaseModel):
    name: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: str
    zone_id: int | None
    profile: dict | None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class DonationIn(BaseModel):
    food_name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=40)
    quantity_kg: float = Field(gt=0, le=10000)
    quantity_meals: int = Field(gt=0, le=10000)
    prepared_at: datetime
    pickup_by: datetime
    storage_type: Literal["ambient", "chilled", "hot", "frozen"]
    zone_id: int
    allergens: list[str] = []
    notes: str | None = Field(default=None, max_length=240)

    @field_validator("allergens")
    @classmethod
    def _clean_allergens(cls, value: list[str]) -> list[str]:
        if len(value) > 10:
            raise ValueError("at most 10 allergens allowed")
        cleaned: list[str] = []
        for item in value:
            norm = item.strip().lower()
            if not 1 <= len(norm) <= 40:
                raise ValueError("each allergen must be 1-40 characters")
            cleaned.append(norm)
        return cleaned


class DonationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    donor_id: int
    donor_name: str
    food_name: str
    category: str
    quantity_kg: float
    quantity_meals: int
    prepared_at: datetime
    pickup_by: datetime
    storage_type: str
    zone_id: int
    zone_name: str
    status: str
    allergens: list[str]
    notes: str | None
    claimed_by_id: int | None
    claimed_by_name: str | None
    created_at: datetime


class RequestIn(BaseModel):
    note: str | None = Field(default=None, max_length=240)


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    donation_id: int
    receiver_id: int
    receiver_name: str
    status: str
    note: str | None
    created_at: datetime
    decided_at: datetime | None


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject"]


class StatusIn(BaseModel):
    to_status: Literal["collected", "delivered"]
