"""Tests for the food-safety window helpers."""

import unittest
from datetime import datetime, timedelta

from backend.services.safety import (
    DISCLAIMER,
    SAFETY_GUIDE,
    effective_pickup_by,
    safety_window_error,
)

NOW = datetime(2030, 1, 1, 12, 0, 0)


class EffectivePickupTests(unittest.TestCase):
    def test_cap_clamps_late_pickup(self):
        prepared = NOW - timedelta(hours=1)
        late = NOW + timedelta(hours=10)
        # ambient cap is 4 hours after preparation.
        self.assertEqual(
            effective_pickup_by(prepared, late, "ambient"),
            prepared + timedelta(hours=4),
        )

    def test_earlier_pickup_is_kept(self):
        prepared = NOW - timedelta(hours=1)
        early = NOW + timedelta(minutes=30)
        self.assertEqual(effective_pickup_by(prepared, early, "ambient"), early)


class SafetyWindowTests(unittest.TestCase):
    def test_valid_window_has_no_error(self):
        self.assertIsNone(
            safety_window_error(
                NOW - timedelta(hours=1), NOW + timedelta(hours=2), "chilled", NOW
            )
        )

    def test_prepared_in_future_is_error(self):
        self.assertIsNotNone(
            safety_window_error(
                NOW + timedelta(minutes=1), NOW + timedelta(hours=2), "ambient", NOW
            )
        )

    def test_pickup_in_past_is_error(self):
        self.assertIsNotNone(
            safety_window_error(
                NOW - timedelta(hours=2), NOW - timedelta(minutes=1), "ambient", NOW
            )
        )

    def test_pickup_before_prepared_is_error(self):
        self.assertIsNotNone(
            safety_window_error(
                NOW - timedelta(hours=1), NOW - timedelta(hours=2), "ambient", NOW
            )
        )


class GuideTests(unittest.TestCase):
    def test_every_storage_type_has_guidance(self):
        self.assertEqual(
            set(SAFETY_GUIDE), {"ambient", "chilled", "hot", "frozen"}
        )

    def test_disclaimer_states_no_certification(self):
        self.assertIn("does not certify food safety", DISCLAIMER)


if __name__ == "__main__":
    unittest.main()
