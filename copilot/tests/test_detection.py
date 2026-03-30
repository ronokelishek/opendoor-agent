"""
tests/test_detection.py
-----------------------
Unit tests for detection/rules.py

Tests cover:
  1. Pricing misalignment fires when thresholds are exceeded (Phoenix mid_tier)
  2. Pricing misalignment does NOT fire for healthy market (Miami)
  3. Inventory aging detection fires correctly (Atlanta)
  4. Funnel deterioration detection fires correctly (Dallas)
  5. Severity assignment logic (magnitude → correct level)
  6. detect_all_issues returns issues sorted by severity
  7. Pricing misalignment: only fires when BOTH conditions are true (not just one)
  8. Issue dataclass validation (invalid severity raises ValueError)

Run with: python -m pytest tests/test_detection.py -v
  or:      python -m unittest tests.test_detection
"""

import os
import sys
import unittest

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.synthetic_data import generate_data
from metrics.calculations import compute_weekly_metrics, compute_wow_changes
from detection.rules import (
    detect_all_issues,
    detect_pricing_misalignment,
    detect_inventory_aging,
    detect_funnel_deterioration,
    detect_margin_compression,
)
from detection.issue_types import Issue, assign_severity, ISSUE_TYPES


# ---------------------------------------------------------------------------
# Fixture: full 12-week synthetic dataset with injected stories
# ---------------------------------------------------------------------------

def _get_full_metrics():
    """Generate and compute metrics for the full 12-week synthetic dataset."""
    df = generate_data()
    metrics = compute_weekly_metrics(df)
    return compute_wow_changes(metrics)


# ---------------------------------------------------------------------------
# Helper: build a minimal metrics DataFrame for targeted tests
# ---------------------------------------------------------------------------

def _make_metrics_row(
    week: int = 10,
    week_start: str = "2024-12-09",
    market: str = "TestMarket",
    segment: str = "mid_tier",
    offer_acceptance_rate: float = 0.72,
    offer_acceptance_rate_wow_delta: float = 0.0,
    lead_to_offer_rate: float = 0.58,
    lead_to_offer_rate_wow_delta: float = 0.0,
    offer_to_close_rate: float = 0.75,
    offer_to_close_rate_wow_delta: float = 0.0,
    avg_offer_vs_market_pct: float = -0.01,
    avg_offer_vs_market_pct_wow_delta: float = 0.0,
    aging_inventory_rate: float = 0.08,
    aging_inventory_rate_wow_delta: float = 0.0,
    avg_days_on_market: float = 28.0,
    avg_days_on_market_wow_delta: float = 0.0,
    avg_acquisition_margin: float = 0.038,
    avg_acquisition_margin_wow_delta: float = 0.0,
    avg_resale_margin: float = 0.054,
    avg_resale_margin_wow_delta: float = 0.0,
    funnel_efficiency: float = 0.22,
    funnel_efficiency_wow_delta: float = 0.0,
    lead_count: int = 40,
    offer_count: int = 24,
    accepted_offer_count: int = 17,
    close_count: int = 13,
    inventory_count: int = 55,
) -> dict:
    """Build a single metrics row dict with sensible defaults."""
    return {
        "week": week,
        "week_start": pd.Timestamp(week_start),
        "market": market,
        "home_segment": segment,
        "offer_acceptance_rate": offer_acceptance_rate,
        "offer_acceptance_rate_wow_delta": offer_acceptance_rate_wow_delta,
        "lead_to_offer_rate": lead_to_offer_rate,
        "lead_to_offer_rate_wow_delta": lead_to_offer_rate_wow_delta,
        "offer_to_close_rate": offer_to_close_rate,
        "offer_to_close_rate_wow_delta": offer_to_close_rate_wow_delta,
        "avg_offer_vs_market_pct": avg_offer_vs_market_pct,
        "avg_offer_vs_market_pct_wow_delta": avg_offer_vs_market_pct_wow_delta,
        "aging_inventory_rate": aging_inventory_rate,
        "aging_inventory_rate_wow_delta": aging_inventory_rate_wow_delta,
        "avg_days_on_market": avg_days_on_market,
        "avg_days_on_market_wow_delta": avg_days_on_market_wow_delta,
        "avg_acquisition_margin": avg_acquisition_margin,
        "avg_acquisition_margin_wow_delta": avg_acquisition_margin_wow_delta,
        "avg_resale_margin": avg_resale_margin,
        "avg_resale_margin_wow_delta": avg_resale_margin_wow_delta,
        "funnel_efficiency": funnel_efficiency,
        "funnel_efficiency_wow_delta": funnel_efficiency_wow_delta,
        "lead_count": lead_count,
        "offer_count": offer_count,
        "accepted_offer_count": accepted_offer_count,
        "close_count": close_count,
        "inventory_count": inventory_count,
    }


def _make_metrics_df(*row_dicts) -> pd.DataFrame:
    """Build a metrics DataFrame from one or more row dicts."""
    return pd.DataFrame(list(row_dicts))


def _two_week_metrics_df(prior: dict, current: dict) -> pd.DataFrame:
    """
    Build a 2-week metrics DataFrame with WoW deltas already set.
    prior = week N-1, current = week N.
    """
    return _make_metrics_df(prior, current)


# ---------------------------------------------------------------------------
# Test 1: Pricing Misalignment fires on Phoenix mid_tier
# ---------------------------------------------------------------------------

class TestPricingMisalignmentDetection(unittest.TestCase):

    def test_fires_on_full_synthetic_data_phoenix(self):
        """
        The full synthetic dataset should detect pricing misalignment
        in Phoenix mid_tier (injected story #1).
        """
        metrics = _get_full_metrics()
        issues = detect_pricing_misalignment(metrics)
        phoenix_issues = [
            i for i in issues if i.market == "Phoenix" and i.segment == "mid_tier"
        ]
        self.assertGreater(
            len(phoenix_issues), 0,
            "Expected pricing misalignment in Phoenix mid_tier but none was detected."
        )

    def test_fires_when_both_thresholds_exceeded(self):
        """Should fire when offer > +2% above market AND acceptance WoW drop > 5%."""
        prior = _make_metrics_row(
            week=9,
            week_start="2024-12-02",
            market="TestCity",
            segment="mid_tier",
            avg_offer_vs_market_pct=0.03,
            offer_acceptance_rate=0.72,
        )
        current = _make_metrics_row(
            week=10,
            week_start="2024-12-09",
            market="TestCity",
            segment="mid_tier",
            avg_offer_vs_market_pct=0.05,  # 5% above market — exceeds 2% warn
            offer_acceptance_rate=0.60,    # Dropped from 0.72 → 0.60 = -12pp
            offer_acceptance_rate_wow_delta=-0.12,
        )
        df = _two_week_metrics_df(prior, current)
        issues = detect_pricing_misalignment(df)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].issue_type, "PRICING_MISALIGNMENT")

    def test_does_not_fire_on_price_above_market_alone(self):
        """Should NOT fire if offer is above market but acceptance rate is stable."""
        prior = _make_metrics_row(
            week=9, week_start="2024-12-02", market="TestCity",
            avg_offer_vs_market_pct=0.03, offer_acceptance_rate=0.72,
        )
        current = _make_metrics_row(
            week=10, week_start="2024-12-09", market="TestCity",
            avg_offer_vs_market_pct=0.05,   # above market
            offer_acceptance_rate=0.73,     # stable — no drop
            offer_acceptance_rate_wow_delta=0.01,
        )
        df = _two_week_metrics_df(prior, current)
        issues = detect_pricing_misalignment(df)
        self.assertEqual(len(issues), 0, "Should not fire without acceptance rate drop")

    def test_does_not_fire_on_acceptance_drop_alone(self):
        """Should NOT fire if acceptance rate drops but offer price is at/below market."""
        prior = _make_metrics_row(
            week=9, week_start="2024-12-02", market="TestCity",
            avg_offer_vs_market_pct=-0.01, offer_acceptance_rate=0.72,
        )
        current = _make_metrics_row(
            week=10, week_start="2024-12-09", market="TestCity",
            avg_offer_vs_market_pct=-0.01,  # below market
            offer_acceptance_rate=0.60,     # dropped
            offer_acceptance_rate_wow_delta=-0.12,
        )
        df = _two_week_metrics_df(prior, current)
        issues = detect_pricing_misalignment(df)
        self.assertEqual(len(issues), 0, "Should not fire without offer above market")

    def test_severity_critical_at_high_deviation(self):
        """Severity should be critical when offer is >4% above market."""
        prior = _make_metrics_row(
            week=9, week_start="2024-12-02", market="TestCity",
            avg_offer_vs_market_pct=0.05, offer_acceptance_rate=0.72,
        )
        current = _make_metrics_row(
            week=10, week_start="2024-12-09", market="TestCity",
            avg_offer_vs_market_pct=0.12,  # 12% above market — critical
            offer_acceptance_rate=0.50,
            offer_acceptance_rate_wow_delta=-0.22,
        )
        df = _two_week_metrics_df(prior, current)
        issues = detect_pricing_misalignment(df)
        self.assertEqual(len(issues), 1)
        self.assertIn(issues[0].severity, ["high", "critical"])


# ---------------------------------------------------------------------------
# Test 2: Pricing Misalignment does NOT fire for Miami
# ---------------------------------------------------------------------------

class TestMiamiHealthyBaseline(unittest.TestCase):

    def test_miami_has_no_pricing_issues(self):
        """
        Miami is the healthy baseline market. Pricing misalignment
        should NOT be detected in Miami.
        """
        metrics = _get_full_metrics()
        issues = detect_pricing_misalignment(metrics)
        miami_issues = [i for i in issues if i.market == "Miami"]
        self.assertEqual(
            len(miami_issues), 0,
            f"Miami should have no pricing issues but detected: {miami_issues}"
        )

    def test_miami_no_issues_overall(self):
        """
        Miami should ideally have no detected issues across all detectors
        in the full synthetic dataset.
        """
        metrics = _get_full_metrics()
        all_issues = detect_all_issues(metrics)
        miami_issues = [i for i in all_issues if i.market == "Miami"]
        # Miami may have 0 or very few issues — it should be much cleaner than others
        other_markets_count = len([i for i in all_issues if i.market != "Miami"])
        self.assertLessEqual(
            len(miami_issues),
            other_markets_count // 3,
            f"Miami has too many issues ({len(miami_issues)}) relative to other markets "
            f"({other_markets_count}). Miami should be the healthy baseline."
        )


# ---------------------------------------------------------------------------
# Test 3: Inventory Aging detection fires correctly (Atlanta)
# ---------------------------------------------------------------------------

class TestInventoryAgingDetection(unittest.TestCase):

    def test_fires_on_full_synthetic_data_atlanta(self):
        """
        The full synthetic dataset should detect inventory aging in Atlanta
        (injected story #2).
        """
        metrics = _get_full_metrics()
        issues = detect_inventory_aging(metrics)
        atlanta_issues = [i for i in issues if i.market == "Atlanta"]
        self.assertGreater(
            len(atlanta_issues), 0,
            "Expected inventory aging in Atlanta but none was detected."
        )

    def test_fires_when_aging_rate_threshold_breached(self):
        """Should fire when aging_inventory_rate > 15%."""
        prior = _make_metrics_row(
            week=9, week_start="2024-12-02", market="TestCity",
            aging_inventory_rate=0.12,
            avg_days_on_market=32.0,
            avg_days_on_market_wow_delta=2.0,
        )
        current = _make_metrics_row(
            week=10, week_start="2024-12-09", market="TestCity",
            aging_inventory_rate=0.18,   # > 15% threshold
            avg_days_on_market=38.0,
            avg_days_on_market_wow_delta=6.0,
        )
        df = _two_week_metrics_df(prior, current)
        issues = detect_inventory_aging(df)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].issue_type, "INVENTORY_AGING")

    def test_fires_on_sustained_dom_increase(self):
        """Should fire when DOM is increasing > 5 days WoW for 2+ weeks."""
        prior = _make_metrics_row(
            week=9, week_start="2024-12-02", market="TestCity",
            aging_inventory_rate=0.10,
            avg_days_on_market=30.0,
            avg_days_on_market_wow_delta=6.0,  # was already increasing last week
        )
        current = _make_metrics_row(
            week=10, week_start="2024-12-09", market="TestCity",
            aging_inventory_rate=0.12,  # below 15% threshold
            avg_days_on_market=37.0,
            avg_days_on_market_wow_delta=7.0,  # increasing again this week
        )
        df = _two_week_metrics_df(prior, current)
        issues = detect_inventory_aging(df)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].issue_type, "INVENTORY_AGING")

    def test_does_not_fire_for_healthy_dom(self):
        """Should NOT fire when aging rate is below threshold and DOM is stable."""
        prior = _make_metrics_row(
            week=9, week_start="2024-12-02", market="TestCity",
            aging_inventory_rate=0.08,
            avg_days_on_market=25.0,
            avg_days_on_market_wow_delta=1.0,
        )
        current = _make_metrics_row(
            week=10, week_start="2024-12-09", market="TestCity",
            aging_inventory_rate=0.09,
            avg_days_on_market=26.5,
            avg_days_on_market_wow_delta=1.5,
        )
        df = _two_week_metrics_df(prior, current)
        issues = detect_inventory_aging(df)
        self.assertEqual(len(issues), 0)


# ---------------------------------------------------------------------------
# Test 4: Funnel Deterioration fires correctly (Dallas)
# ---------------------------------------------------------------------------

class TestFunnelDeteriorationDetection(unittest.TestCase):

    def test_fires_on_full_synthetic_data_dallas(self):
        """
        The full synthetic dataset should detect funnel deterioration in Dallas
        (injected story #3).
        """
        metrics = _get_full_metrics()
        issues = detect_funnel_deterioration(metrics)
        dallas_issues = [i for i in issues if i.market == "Dallas"]
        self.assertGreater(
            len(dallas_issues), 0,
            "Expected funnel deterioration in Dallas but none was detected."
        )

    def test_fires_on_l2o_drop(self):
        """Should fire when lead-to-offer rate WoW drop > 3%."""
        prior = _make_metrics_row(
            week=9, week_start="2024-12-02", market="TestCity",
            lead_to_offer_rate=0.58,
        )
        current = _make_metrics_row(
            week=10, week_start="2024-12-09", market="TestCity",
            lead_to_offer_rate=0.50,       # Dropped 8pp — exceeds 3% threshold
            lead_to_offer_rate_wow_delta=-0.08,
        )
        df = _two_week_metrics_df(prior, current)
        issues = detect_funnel_deterioration(df)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].issue_type, "FUNNEL_DETERIORATION")

    def test_fires_on_o2c_drop(self):
        """Should fire when offer-to-close rate WoW drop > 4%."""
        prior = _make_metrics_row(
            week=9, week_start="2024-12-02", market="TestCity",
            offer_to_close_rate=0.78,
        )
        current = _make_metrics_row(
            week=10, week_start="2024-12-09", market="TestCity",
            offer_to_close_rate=0.68,       # Dropped 10pp — exceeds 4% threshold
            offer_to_close_rate_wow_delta=-0.10,
        )
        df = _two_week_metrics_df(prior, current)
        issues = detect_funnel_deterioration(df)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].issue_type, "FUNNEL_DETERIORATION")

    def test_does_not_fire_for_stable_funnel(self):
        """Should NOT fire when funnel rates are stable."""
        prior = _make_metrics_row(
            week=9, week_start="2024-12-02", market="TestCity",
            lead_to_offer_rate=0.58,
            offer_to_close_rate=0.75,
        )
        current = _make_metrics_row(
            week=10, week_start="2024-12-09", market="TestCity",
            lead_to_offer_rate=0.57,      # 1pp drop — below 3% threshold
            lead_to_offer_rate_wow_delta=-0.01,
            offer_to_close_rate=0.73,     # 2pp drop — below 4% threshold
            offer_to_close_rate_wow_delta=-0.02,
        )
        df = _two_week_metrics_df(prior, current)
        issues = detect_funnel_deterioration(df)
        self.assertEqual(len(issues), 0)


# ---------------------------------------------------------------------------
# Test 5: Severity assignment logic
# ---------------------------------------------------------------------------

class TestSeverityAssignment(unittest.TestCase):

    def test_low_severity_below_warn(self):
        """Value below warn threshold → low severity."""
        sev = assign_severity(value=0.01, warn=0.05, critical=0.10)
        self.assertEqual(sev, "low")

    def test_medium_severity_at_warn(self):
        """Value at warn threshold → medium severity."""
        sev = assign_severity(value=0.05, warn=0.05, critical=0.10)
        self.assertEqual(sev, "medium")

    def test_high_severity_at_critical(self):
        """Value at critical threshold → high severity."""
        sev = assign_severity(value=0.10, warn=0.05, critical=0.10)
        self.assertEqual(sev, "high")

    def test_critical_severity_double_critical(self):
        """Value >= 2x critical threshold → critical severity."""
        sev = assign_severity(value=0.21, warn=0.05, critical=0.10)
        self.assertEqual(sev, "critical")

    def test_severity_between_warn_and_critical(self):
        """Value between warn and critical → medium severity."""
        sev = assign_severity(value=0.07, warn=0.05, critical=0.10)
        self.assertEqual(sev, "medium")


# ---------------------------------------------------------------------------
# Test 6: detect_all_issues returns issues sorted by severity
# ---------------------------------------------------------------------------

class TestDetectAllIssues(unittest.TestCase):

    def test_returns_list(self):
        """detect_all_issues should return a list."""
        metrics = _get_full_metrics()
        issues = detect_all_issues(metrics)
        self.assertIsInstance(issues, list)

    def test_sorted_by_severity_descending(self):
        """
        Issues should be sorted critical → high → medium → low.
        """
        metrics = _get_full_metrics()
        issues = detect_all_issues(metrics)
        if len(issues) < 2:
            self.skipTest("Not enough issues to test sorting")

        severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        ranks = [severity_rank[i.severity] for i in issues]
        self.assertEqual(
            ranks,
            sorted(ranks, reverse=True),
            "Issues are not sorted by severity descending."
        )

    def test_detects_injected_stories(self):
        """
        The three injected problem markets should all produce detected issues.
        Miami should be the cleanest market.
        """
        metrics = _get_full_metrics()
        issues = detect_all_issues(metrics)

        affected_markets = {i.market for i in issues}

        # All three injected problem markets should appear
        self.assertIn("Phoenix", affected_markets, "Phoenix issue not detected")
        self.assertIn("Atlanta", affected_markets, "Atlanta issue not detected")
        self.assertIn("Dallas", affected_markets, "Dallas issue not detected")


# ---------------------------------------------------------------------------
# Test 7: Issue dataclass validation
# ---------------------------------------------------------------------------

class TestIssueDataclass(unittest.TestCase):

    def test_valid_issue_creates_successfully(self):
        """Valid Issue object should be created without errors."""
        issue = Issue(
            issue_id="TEST_001",
            issue_type="PRICING_MISALIGNMENT",
            market="Phoenix",
            segment="mid_tier",
            severity="high",
            week_start="2024-12-09",
            title="Test Issue",
            evidence=["Evidence 1"],
            metrics_snapshot={"offer_acceptance_rate": 0.60},
            wow_deltas={"offer_acceptance_rate_wow_delta": -0.12},
            confidence="High",
        )
        self.assertEqual(issue.market, "Phoenix")
        self.assertEqual(issue.severity, "high")
        self.assertEqual(issue.owner, "pricing")  # Auto-populated from ISSUE_TYPES

    def test_invalid_severity_raises_value_error(self):
        """Invalid severity should raise ValueError."""
        with self.assertRaises(ValueError):
            Issue(
                issue_id="TEST_002",
                issue_type="PRICING_MISALIGNMENT",
                market="Phoenix",
                segment="mid_tier",
                severity="extreme",  # Invalid
                week_start="2024-12-09",
                title="Test",
                confidence="High",
            )

    def test_severity_rank_ordering(self):
        """Severity rank should order critical > high > medium > low."""
        def make_issue(severity):
            return Issue(
                issue_id=f"TEST_{severity}",
                issue_type="PRICING_MISALIGNMENT",
                market="TestMarket",
                segment="mid_tier",
                severity=severity,
                week_start="2024-12-09",
                title="Test",
                confidence="High",
            )

        critical = make_issue("critical")
        high = make_issue("high")
        medium = make_issue("medium")
        low = make_issue("low")

        self.assertGreater(critical.severity_rank(), high.severity_rank())
        self.assertGreater(high.severity_rank(), medium.severity_rank())
        self.assertGreater(medium.severity_rank(), low.severity_rank())

    def test_to_dict_is_json_serializable(self):
        """Issue.to_dict() should produce a JSON-serializable dict."""
        import json
        issue = Issue(
            issue_id="TEST_003",
            issue_type="INVENTORY_AGING",
            market="Atlanta",
            segment="entry_level",
            severity="medium",
            week_start="2024-12-09",
            title="Test Inventory Issue",
            evidence=["DOM is rising"],
            metrics_snapshot={"avg_days_on_market": 35.5},
            wow_deltas={"avg_days_on_market_wow_delta": 6.5},
            confidence="Medium-High",
        )
        d = issue.to_dict()
        serialized = json.dumps(d)  # Should not raise
        self.assertIn("INVENTORY_AGING", serialized)
        self.assertIn("Atlanta", serialized)


if __name__ == "__main__":
    unittest.main(verbosity=2)
