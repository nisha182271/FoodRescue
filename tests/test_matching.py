"""Tests for the pure matching functions."""

import unittest
from datetime import datetime, timedelta

from backend.core.geo import haversine_km
from backend.services.matching import rank_donations, score_donation

NOW = datetime(2030, 1, 1, 12, 0, 0)
LAT, LNG = 51.5, -0.12


def _donation(**overrides):
    d = {
        "meals": 40,
        "lat": LAT,
        "lng": LNG,
        "pickup_by": NOW + timedelta(hours=3),
        "prepared_at": NOW - timedelta(hours=1),
        "storage_type": "ambient",
        "category": "cooked",
        "allergens": [],
    }
    d.update(overrides)
    return d


def _receiver(**overrides):
    r = {
        "lat": LAT,
        "lng": LNG,
        "radius_km": 10.0,
        "capacity_meals": 40,
        "accepts_categories": [],
        "excluded_allergens": [],
        "can_store_chilled": False,
    }
    r.update(overrides)
    return r


class HaversineTests(unittest.TestCase):
    def test_one_degree_latitude_is_about_111_km(self):
        self.assertAlmostEqual(haversine_km(0, 0, 1, 0), 111.2, delta=0.5)

    def test_same_point_is_zero(self):
        self.assertAlmostEqual(haversine_km(LAT, LNG, LAT, LNG), 0.0)


class HardFilterTests(unittest.TestCase):
    def test_outside_radius_rejected(self):
        far = _receiver(lat=LAT + 1.0, radius_km=10.0)
        result = score_donation(_donation(), far, NOW)
        self.assertFalse(result["eligible"])
        self.assertEqual(result["reason"], "outside search radius")

    def test_excluded_allergen_rejected(self):
        result = score_donation(
            _donation(allergens=["nuts"]),
            _receiver(excluded_allergens=["nuts"]),
            NOW,
        )
        self.assertFalse(result["eligible"])
        self.assertEqual(result["reason"], "contains an excluded allergen")

    def test_category_not_accepted_rejected(self):
        result = score_donation(
            _donation(category="bakery"),
            _receiver(accepts_categories=["cooked"]),
            NOW,
        )
        self.assertFalse(result["eligible"])
        self.assertEqual(result["reason"], "category not accepted")

    def test_chilled_without_capability_rejected(self):
        result = score_donation(
            _donation(storage_type="chilled"),
            _receiver(can_store_chilled=False),
            NOW,
        )
        self.assertFalse(result["eligible"])
        self.assertEqual(result["reason"], "receiver cannot store chilled food")

    def test_pickup_window_too_short_rejected(self):
        result = score_donation(
            _donation(pickup_by=NOW + timedelta(minutes=5)),
            _receiver(lat=LAT + 0.05),
            NOW,
        )
        self.assertFalse(result["eligible"])
        self.assertEqual(result["reason"], "pickup window too short")


class ScoringTests(unittest.TestCase):
    def test_eligible_result_has_breakdown(self):
        result = score_donation(_donation(), _receiver(), NOW)
        self.assertTrue(result["eligible"])
        self.assertIsNone(result["reason"])
        self.assertEqual(
            set(result["breakdown"]), {"distance", "quantity", "urgency", "need"}
        )
        self.assertLessEqual(result["score"], 100.0)

    def test_closer_scores_higher_distance(self):
        near = score_donation(_donation(), _receiver(), NOW)
        farther = score_donation(_donation(), _receiver(lat=LAT + 0.05), NOW)
        self.assertGreater(
            near["breakdown"]["distance"], farther["breakdown"]["distance"]
        )

    def test_matching_quantity_scores_higher(self):
        exact = score_donation(_donation(meals=40), _receiver(capacity_meals=40), NOW)
        off = score_donation(_donation(meals=10), _receiver(capacity_meals=40), NOW)
        self.assertGreater(exact["breakdown"]["quantity"], off["breakdown"]["quantity"])

    def test_sooner_deadline_scores_higher_urgency(self):
        relaxed = score_donation(
            _donation(pickup_by=NOW + timedelta(hours=5)), _receiver(), NOW
        )
        urgent = score_donation(
            _donation(pickup_by=NOW + timedelta(hours=1)), _receiver(), NOW
        )
        self.assertGreater(
            urgent["breakdown"]["urgency"], relaxed["breakdown"]["urgency"]
        )

    def test_explicit_category_gets_full_need_points(self):
        explicit = score_donation(
            _donation(), _receiver(accepts_categories=["cooked"]), NOW
        )
        open_ = score_donation(_donation(), _receiver(), NOW)
        self.assertEqual(explicit["breakdown"]["need"], 15.0)
        self.assertEqual(open_["breakdown"]["need"], 12.0)


class RankTests(unittest.TestCase):
    def test_rank_keeps_only_eligible_and_sorts_by_score(self):
        strong = _donation(meals=40)
        weak = _donation(meals=5)
        blocked = _donation(allergens=["nuts"])
        strong["id"], weak["id"], blocked["id"] = 1, 2, 3
        receiver = _receiver(excluded_allergens=["nuts"])
        ranked = rank_donations([weak, blocked, strong], receiver, NOW)
        self.assertEqual([r["id"] for r in ranked], [1, 2])
        self.assertGreaterEqual(ranked[0]["score"], ranked[1]["score"])


if __name__ == "__main__":
    unittest.main()
