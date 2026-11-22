"""Application configuration for FoodRescue (standard library only)."""

import os
from pathlib import Path

# foodrescue-v2/backend/core/config.py -> parents[2] is foodrescue-v2
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "foodrescue.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

# Maximum hours of guidance before pickup, per storage type.
# These are demo values for guidance only, NOT a food-safety certification.
SAFETY_CAP_HOURS = {
    "ambient": 4,
    "chilled": 6,
    "hot": 4,
    "frozen": 24,
}

# Token signing. Override FOODRESCUE_SECRET outside development.
SECRET_KEY = os.environ.get("FOODRESCUE_SECRET", "dev-only-change-me")
TOKEN_TTL_HOURS = 12

# Matching weights (sum to 100). Demo values, not tuned on real data.
MATCH_WEIGHTS = {"distance": 35, "quantity": 25, "urgency": 25, "need": 15}
MATCH_BUFFER_MINUTES = 15
AVERAGE_SPEED_KMH = 20.0
DEFAULT_RADIUS_KM = 10.0
# Assumption for demonstration impact figures: 1 kg of food ~ 2 meals.
MEALS_PER_KG = 2.0
