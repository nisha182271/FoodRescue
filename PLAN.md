# FoodRescue – Smart Surplus Food Redistribution Platform: Plan

## 1. Requirement analysis
| # | Requirement | What it needs |
|---|---|---|
| 1 | Donor registration and listing | Accounts with role = donor; donor profile with business type and zone |
| 2 | Food information | Name, category, quantity (kg and meals), prepared-at, pickup-by, storage type, allergens |
| 3 | Receiver registration and discovery | Accounts with role = receiver; org type, capacity, needs, zone; search and map |
| 4 | Smart matching | Distance, quantity, time window, receiver needs and safety constraints |
| 5 | Pickup statuses | Posted → Claimed → Collected → Delivered, with audit trail |
| 6 | Impact dashboard | Meals saved, kg diverted, estimated waste avoided (assumptions stated) |
| 7 | Food safety guidance | Storage and time limits shown in UI and enforced by server |
| 8 | Business model | Static page for donors, sponsors and CSR partners; no tax or legal claims |

Restrictions: synthetic data only; locations are named zones with approximate coordinates (no real addresses); no personal contact data stored or shown; never claim food-safety certification; visible disclaimer on every donation; no tax or legal promises.

## 2. Architecture
Modular monolith, one process:
- frontend/ (HTML/CSS/JS, served by FastAPI): index (discover + map), donor, receiver, pickups, impact, safety, business
- backend/api/ routers: auth, donations, matches, pickups, impact, meta
- backend/services/ matching.py, pickup_state.py, safety.py, impact.py
- backend/core/ config (weights, safety table), geo (haversine), security (hash, token)
- backend/db/ SQLAlchemy models, session, seed.py (synthetic data)
- data/foodrescue.db (SQLite, WAL mode)

Choices: Leaflet with OpenStreetMap tiles for the map (list view works without it); fixed zone coordinates instead of geocoding; stdlib PBKDF2 password hashing and HMAC-signed bearer tokens; all timestamps stored as UTC and sent with a Z suffix; Python 3.11 pinned.

## 3. Database design
| Table | Key columns | Relationships |
|---|---|---|
| users | id, role (donor/receiver/volunteer), name, password_hash, created_at | 1:1 donor_profiles, 1:1 receiver_profiles |
| donor_profiles | user_id (PK/FK), business_type (restaurant, caterer, venue, hostel, canteen), zone_id | users, zones |
| receiver_profiles | user_id (PK/FK), org_type (ngo, kitchen, shelter, volunteer_group), zone_id, daily_capacity_meals, accepts_categories (JSON), excluded_allergens (JSON), can_store_chilled (bool) | users, zones |
| zones | id, name, lat, lng | synthetic; referenced by profiles and donations |
| donations | id, donor_id, food_name, category, quantity_kg, quantity_meals, prepared_at, pickup_by, storage_type (ambient/chilled/hot/frozen), zone_id, lat, lng, status, claimed_by_id, claimed_at, collected_at, delivered_at, created_at | donor and claimed_by → users; zone → zones |
| donation_allergens | donation_id, allergen | many-to-one donations |
| status_events | id, donation_id, from_status, to_status, actor_id, at | audit trail; many-to-one donations |

pickup_by is stored as the earlier of the donor's deadline and prepared_at plus the maximum safe hours for the storage type; the server enforces this.

## 4. API endpoints
| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | /api/auth/register | public | Create donor or receiver account |
| POST | /api/auth/login | public | Returns bearer token |
| GET | /api/me | any | Current user and profile |
| GET | /api/meta/zones | public | Zones for dropdowns and map |
| GET | /api/meta/safety | public | Storage types, max hours, guidance, disclaimer |
| POST | /api/donations | donor | Create listing (server applies safety cap) |
| GET | /api/donations/mine | donor | Own listings with status |
| PATCH | /api/donations/{id} | donor | Edit only while posted |
| POST | /api/donations/{id}/cancel | donor | Cancel before collection |
| GET | /api/donations | public | Discovery: status=posted, zone, category, radius_km |
| GET | /api/donations/{id} | public | Detail with safety notes and allergens |
| GET | /api/matches | receiver | Ranked matches with score breakdown |
| POST | /api/donations/{id}/claim | receiver | Atomic conditional claim |
| POST | /api/donations/{id}/status | receiver or volunteer | claimed → collected → delivered |
| GET | /api/donations/{id}/events | donor, claimant | Status timeline |
| GET | /api/impact | public | Aggregates: meals, kg, waste avoided, counts |

Invalid status transitions return 409.

## 5. Smart matching algorithm
Step 1 – hard filters (excluded if any fails):
- status is posted
- now + travel time + 15 min buffer ≤ pickup_by
- distance ≤ receiver radius (default 10 km)
- no excluded allergen in the donation
- category accepted (or receiver accepts all)
- chilled donations only to receivers who can store chilled

Step 2 – score 0 to 100:
| Factor | Weight | Formula |
|---|---|---|
| Distance | 35 | 35 × (1 − distance / radius) |
| Quantity fit | 25 | 25 × min(meals, need) / max(meals, need), need = receiver daily capacity |
| Urgency | 25 | Higher when remaining feasible window is short, so food is used before it expires |
| Need match | 15 | 15 if preferred category, 8 if accepted only |

Travel time = distance ÷ 20 km/h; distance = haversine on zone coordinates.
Output: sorted list with total and per-factor points. Ties break on earlier pickup_by.
The algorithm recommends; a human clicks Claim. Claims are atomic (conditional UPDATE where status = 'posted', check rowcount) so two receivers cannot both take the same food.
Tested as pure functions with fixed inputs.

## 6. 48-hour development sequence
| Hours | Work | Done when |
|---|---|---|
| 0–4 | Repo layout, models, seed script (6 zones, 6 donors, 6 receivers, ~20 donations), auth | Seed runs; login works |
| 4–12 | Donation CRUD, safety rules, deadline cap, status machine | Donor can post; invalid transitions return 409 |
| 12–20 | Matching service, /api/matches, unit tests | Ranked results with breakdown; tests pass |
| 20–28 | Donor page (form with safety guidance), receiver discovery list | Post then discover end to end |
| 28–34 | Claim flow, pickup timeline, Leaflet map | Two simultaneous claims: one 200, one 409 |
| 34–40 | Impact dashboard, safety page, business page | All 8 requirements visibly covered |
| 40–44 | Error messages, responsive CSS, README, demo script | Feature freeze at hour 40 |
| 44–48 | Rehearse demo twice, fallback video, slides | Demo runs from clean seed |

Cut line: if behind at hour 28, drop the map first, then the volunteer role. Keep matching, safety and statuses.

## 7. Technical risks
| Risk | Impact | Mitigation |
|---|---|---|
| Eight features in 48 hours | High | Cut line; core flow is post → discover → match → claim → deliver |
| Timezone bugs returning | High | UTC everywhere, Z suffix, one "now" helper, tests on a non-UTC machine |
| Claim race | High | Conditional UPDATE, rowcount check, concurrent-call test |
| Auth bugs | Medium | Simple token; tests that anonymous claims get 401 |
| Map needs internet | Medium | List view is primary; map is enhancement |
| Food-safety liability | High | Show time limits and "not a safety certification" notice; enforce deadlines server-side; never call food "safe" |
| Matching looks like a black box | Medium | Show score breakdown in UI |
| Impact numbers look invented | Medium | Label assumptions (e.g. 2 meals per kg; waste avoided = diverted kg); show formula |
| Synthetic data looks fake | Low | Realistic menus and zone names; no real addresses |
| fromisoformat needs Python 3.11+ for Z suffix | Low | Pin Python 3.11 in README; version-safe parser |
| SQLite concurrency | Low | Fine for demo load; WAL mode |
