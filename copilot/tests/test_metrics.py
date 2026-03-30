"""
tests/test_metrics.py
---------------------
Unit tests for metrics/calculations.py

Tests cover:
  1. offer_acceptance_rate calculation correctness
  2. lead_to_offer_rate calculation correctness
  3. WoW delta calculation (correct sign and magnitude)
  4. Edge case: zero division (no offers → NaN, not crash)
  5. Edge case: single week (no prior → WoW delta is NaN)
  6. Market/segment filtering in snapshot
  7. Funnel efficiency end-to-end

Run with: python -m pytest tests/test_metrics.py -v
  or:      python -m unittest tests.test_metrics
"""

import os
import sys
import unittest
import math

import pandas as pd
import numpy as np

# Ensure the copilot package root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metrics.calculations import (
    compute_weekly_metrics,
    compute_wow_changes,
    get_market_segment_snapshot,
)


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------

def _make_raw_df(rows: list) -> pd.DataFrame:
    """
    Build a minimal raw DataFrame suitable for compute_weekly_metrics.
    Each item in rows is a dict with required fields.
    Defaults are provided for missing optional columns.
    """
    defaults = {
        "week": 1,
        "week_start": pd.Timestamp("2024-10-07"),
        "market": "TestMarket",
        "zip_code": "00001",
        "home_segment": "mid_tier",
        "list_price": 400_000,
        "opendoor_offer_price": 396_000,
        "market_estimated_value": 400_000,
        "seller_accepted_offer": True,
        "days_to_accept": 4.0,
        "lead_count": 40,
        "offer_count": 24,
        "accepted_offer_count": 17,
        "close_count": 13,
        "inventory_days_on_market": 28.0,
        "inventory_count": 55,
        "acquisition_margin_estimate": 0.038,
        "resale_margin_estimate": 0.054,
    }
    all_rows = []
    for row in rows:
        merged = {**defaults, **row}
        all_rows.append(merged)
    df = pd.DataFrame(all_rows)
    df["week_start"] = pd.to_datetime(df["week_start"])
    return df


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestOfferAcceptanceRate(unittest.TestCase):
    """Test 1: offer_acceptance_rate = accepted_offer_count / offer_count"""

    def test_basic_calculation(self):
        """Acceptance rate should equal accepted_offer_count / offer_count."""
        raw = _make_raw_df([{
            "offer_count": 20,
            "accepted_offer_count": 15,
        }])
        metrics = compute_weekly_metrics(raw)
        rate = metrics.iloc[0]["offer_acceptance_rate"]
        self.assertAlmostEqual(rate, 15 / 20, places=4)

    def test_perfect_acceptance(self):
        """100% acceptance rate when all offers are accepted."""
        raw = _make_raw_df([{
            "offer_count": 10,
            "accepted_offer_count": 10,
        }])
        metrics = compute_weekly_metrics(raw)
        rate = metrics.iloc[0]["offer_acceptance_rate"]
        self.assertAlmostEqual(rate, 1.0, places=4)

    def test_low_acceptance(self):
        """Very low acceptance rate is computed correctly."""
        raw = _make_raw_df([{
            "offer_count": 100,
            "accepted_offer_count": 10,
        }])
        metrics = compute_weekly_metrics(raw)
        rate = metrics.iloc[0]["offer_acceptance_rate"]
        self.assertAlmostEqual(rate, 0.10, places=4)

    def test_aggregation_across_zips(self):
        """
        When multiple zip codes exist for same (week, market, segment),
        acceptance rate should be computed on the summed counts, not averaged rates.
        """
        raw = _make_raw_df([
            {"zip_code": "00001", "offer_count": 10, "accepted_offer_count": 8},
            {"zip_code": "00002", "offer_count": 10, "accepted_offer_count": 4},
        ])
        metrics = compute_weekly_metrics(raw)
        # Total: 12 / 20 = 0.60 (NOT avg of 0.8 and 0.4 = 0.60 — same here but matters at unequal volumes)
        rate = metrics.iloc[0]["offer_acceptance_rate"]
        self.assertAlmostEqual(rate, 12 / 20, places=4)

    def test_aggregation_unequal_volumes(self):
        """
        Acceptance rate must be computed on summed counts, not avg of rates.
        Two zips: 9/10 and 1/10 → 10/20 = 0.50 (not avg of 0.9+0.1 = 0.50 — different when volumes differ)
        """
        raw = _make_raw_df([
            {"zip_code": "00001", "offer_count": 100, "accepted_offer_count": 90},
            {"zip_code": "00002", "offer_count": 10,  "accepted_offer_count": 1},
        ])
        metrics = compute_weekly_metrics(raw)
        expected = 91 / 110  # ≈ 0.827 — very different from avg of 0.9 and 0.1
        rate = metrics.iloc[0]["offer_acceptance_rate"]
        self.assertAlmostEqual(rate, expected, places=4)


class TestLeadToOfferRate(unittest.TestCase):
    """Test 2: lead_to_offer_rate = offer_count / lead_count"""

    def test_basic_calculation(self):
        raw = _make_raw_df([{
            "lead_count": 50,
            "offer_count": 30,
        }])
        metrics = compute_weekly_metrics(raw)
        rate = metrics.iloc[0]["lead_to_offer_rate"]
        self.assertAlmostEqual(rate, 30 / 50, places=4)

    def test_funnel_efficiency_end_to_end(self):
        """funnel_efficiency = close_count / lead_count"""
        raw = _make_raw_df([{
            "lead_count": 100,
            "offer_count": 60,
            "accepted_offer_count": 45,
            "close_count": 36,
        }])
        metrics = compute_weekly_metrics(raw)
        eff = metrics.iloc[0]["funnel_efficiency"]
        self.assertAlmostEqual(eff, 36 / 100, places=4)


class TestEdgeCaseZeroDivision(unittest.TestCase):
    """Test 3: Zero division should return NaN, not raise an exception."""

    def test_zero_offers_acceptance_rate(self):
        """offer_acceptance_rate should be NaN when offer_count == 0."""
        raw = _make_raw_df([{
            "offer_count": 0,
            "accepted_offer_count": 0,
        }])
        metrics = compute_weekly_metrics(raw)
        rate = metrics.iloc[0]["offer_acceptance_rate"]
        self.assertTrue(math.isnan(rate), f"Expected NaN, got {rate}")

    def test_zero_leads_lead_to_offer_rate(self):
        """lead_to_offer_rate should be NaN when lead_count == 0."""
        raw = _make_raw_df([{
            "lead_count": 0,
            "offer_count": 0,
        }])
        metrics = compute_weekly_metrics(raw)
        rate = metrics.iloc[0]["lead_to_offer_rate"]
        self.assertTrue(math.isnan(rate), f"Expected NaN, got {rate}")

    def test_zero_accepted_offers_o2c_rate(self):
        """offer_to_close_rate should be NaN when accepted_offer_count == 0."""
        raw = _make_raw_df([{
            "accepted_offer_count": 0,
            "close_count": 0,
        }])
        metrics = compute_weekly_metrics(raw)
        rate = metrics.iloc[0]["offer_to_close_rate"]
        self.assertTrue(math.isnan(rate), f"Expected NaN, got {rate}")


class TestWoWDeltas(unittest.TestCase):
    """Test 4: WoW delta = current week value - prior week value"""

    def _two_week_df(
        self,
        wk1_accept: float,
        wk2_accept: float,
        offer_count: int = 20,
    ) -> pd.DataFrame:
        """Helper: build two weeks of data with specified acceptance rates."""
        raw = _make_raw_df([
            {
                "week": 1,
                "week_start": pd.Timestamp("2024-10-07"),
                "offer_count": offer_count,
                "accepted_offer_count": int(offer_count * wk1_accept),
            },
            {
                "week": 2,
                "week_start": pd.Timestamp("2024-10-14"),
                "offer_count": offer_count,
                "accepted_offer_count": int(offer_count * wk2_accept),
            },
        ])
        metrics = compute_weekly_metrics(raw)
        return compute_wow_changes(metrics)

    def test_wow_delta_positive_improvement(self):
        """If acceptance rate goes from 0.60 to 0.70, delta should be +0.10."""
        df = self._two_week_df(0.60, 0.70)
        wk2 = df[df["week"] == 2].iloc[0]
        delta = wk2["offer_acceptance_rate_wow_delta"]
        self.assertAlmostEqual(delta, 0.10, places=3)

    def test_wow_delta_negative_decline(self):
        """If acceptance rate goes from 0.70 to 0.55, delta should be -0.15."""
        df = self._two_week_df(0.70, 0.55)
        wk2 = df[df["week"] == 2].iloc[0]
        delta = wk2["offer_acceptance_rate_wow_delta"]
        self.assertAlmostEqual(delta, -0.15, places=3)

    def test_wow_delta_first_week_is_nan(self):
        """First week in a series should have NaN WoW delta (no prior week)."""
        df = self._two_week_df(0.65, 0.72)
        wk1 = df[df["week"] == 1].iloc[0]
        delta = wk1["offer_acceptance_rate_wow_delta"]
        self.assertTrue(math.isnan(delta), f"Expected NaN for first week, got {delta}")

    def test_wow_delta_independent_by_market_segment(self):
        """
        WoW deltas must be computed within market-segment groups.
        Market A week 2 delta should not be influenced by Market B data.
        """
        raw = _make_raw_df([
            # Market A: rate drops from 0.8 to 0.6
            {
                "week": 1,
                "week_start": pd.Timestamp("2024-10-07"),
                "market": "MarketA",
                "offer_count": 10,
                "accepted_offer_count": 8,
            },
            {
                "week": 2,
                "week_start": pd.Timestamp("2024-10-14"),
                "market": "MarketA",
                "offer_count": 10,
                "accepted_offer_count": 6,
            },
            # Market B: rate is constant 0.5
            {
                "week": 1,
                "week_start": pd.Timestamp("2024-10-07"),
                "market": "MarketB",
                "offer_count": 10,
                "accepted_offer_count": 5,
            },
            {
                "week": 2,
                "week_start": pd.Timestamp("2024-10-14"),
                "market": "MarketB",
                "offer_count": 10,
                "accepted_offer_count": 5,
            },
        ])
        metrics = compute_weekly_metrics(raw)
        wow = compute_wow_changes(metrics)

        mkt_a_wk2 = wow[(wow["market"] == "MarketA") & (wow["week"] == 2)].iloc[0]
        mkt_b_wk2 = wow[(wow["market"] == "MarketB") & (wow["week"] == 2)].iloc[0]

        self.assertAlmostEqual(mkt_a_wk2["offer_acceptance_rate_wow_delta"], -0.20, places=3)
        self.assertAlmostEqual(mkt_b_wk2["offer_acceptance_rate_wow_delta"], 0.00, places=3)


class TestMarketSegmentSnapshot(unittest.TestCase):
    """Test 5: get_market_segment_snapshot returns correct structure and values"""

    def setUp(self):
        """Build a small 3-week dataset for snapshot tests."""
        from data.synthetic_data import generate_data
        df = generate_data()
        metrics = compute_weekly_metrics(df)
        self.metrics_wow = compute_wow_changes(metrics)

    def test_snapshot_returns_expected_keys(self):
        """Snapshot should have market, segment, week, current, prior, deltas."""
        snap = get_market_segment_snapshot(self.metrics_wow, "Miami", "mid_tier")
        self.assertIn("market", snap)
        self.assertIn("segment", snap)
        self.assertIn("week", snap)
        self.assertIn("week_start", snap)
        self.assertIn("current", snap)
        self.assertIn("prior", snap)
        self.assertIn("deltas", snap)

    def test_snapshot_market_filter(self):
        """Snapshot should return data only for the requested market."""
        snap = get_market_segment_snapshot(self.metrics_wow, "Phoenix", "mid_tier")
        self.assertEqual(snap["market"], "Phoenix")
        self.assertEqual(snap["segment"], "mid_tier")

    def test_snapshot_current_has_metrics(self):
        """Current metrics dict should contain offer_acceptance_rate."""
        snap = get_market_segment_snapshot(self.metrics_wow, "Atlanta", "entry_level")
        self.assertIn("offer_acceptance_rate", snap["current"])
        rate = snap["current"]["offer_acceptance_rate"]
        self.assertIsNotNone(rate)
        self.assertGreater(rate, 0.0)
        self.assertLessEqual(rate, 1.0)

    def test_snapshot_empty_for_nonexistent_market(self):
        """Snapshot should return empty dict for a market that doesn't exist."""
        snap = get_market_segment_snapshot(self.metrics_wow, "NonExistent", "mid_tier")
        self.assertEqual(snap, {})

    def test_snapshot_specific_week(self):
        """Requesting a specific week should return that week's data."""
        snap = get_market_segment_snapshot(self.metrics_wow, "Dallas", "mid_tier", week=6)
        self.assertEqual(snap["week"], 6)


class TestAvgOfferVsMarket(unittest.TestCase):
    """Test 6: avg_offer_vs_market_pct calculation"""

    def test_offer_above_market(self):
        """If offer price > market value, metric should be positive."""
        raw = _make_raw_df([{
            "opendoor_offer_price": 420_000,
            "market_estimated_value": 400_000,
        }])
        metrics = compute_weekly_metrics(raw)
        pct = metrics.iloc[0]["avg_offer_vs_market_pct"]
        self.assertAlmostEqual(pct, 0.05, places=4)

    def test_offer_below_market(self):
        """If offer price < market value, metric should be negative."""
        raw = _make_raw_df([{
            "opendoor_offer_price": 380_000,
            "market_estimated_value": 400_000,
        }])
        metrics = compute_weekly_metrics(raw)
        pct = metrics.iloc[0]["avg_offer_vs_market_pct"]
        self.assertAlmostEqual(pct, -0.05, places=4)

    def test_offer_equals_market(self):
        """If offer price == market value, metric should be 0."""
        raw = _make_raw_df([{
            "opendoor_offer_price": 400_000,
            "market_estimated_value": 400_000,
        }])
        metrics = compute_weekly_metrics(raw)
        pct = metrics.iloc[0]["avg_offer_vs_market_pct"]
        self.assertAlmostEqual(pct, 0.0, places=4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
