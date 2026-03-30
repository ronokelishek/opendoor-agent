"""
synthetic_data.py
-----------------
Generates 12 weeks of realistic synthetic real estate market data for the
Opendoor Pricing & Conversion Copilot demo.

Four market stories are injected deliberately:
  1. Phoenix (mid_tier)   — Pricing misalignment starting week 8
  2. Atlanta (all)        — Inventory aging starting week 6
  3. Dallas (all)         — Funnel deterioration starting week 7
  4. Miami (all)          — Healthy baseline (control market)

Run standalone to write output/synthetic_data.csv.
"""

import random
import math
import os
import sys
from datetime import date, timedelta

import pandas as pd

# ---------------------------------------------------------------------------
# Seed for reproducibility
# ---------------------------------------------------------------------------
random.seed(42)

# ---------------------------------------------------------------------------
# Market / segment / zip configuration
# ---------------------------------------------------------------------------
MARKETS = ["Phoenix", "Atlanta", "Dallas", "Miami"]

ZIP_CODES = {
    "Phoenix": ["85001", "85004", "85008"],
    "Atlanta": ["30301", "30305", "30309"],
    "Dallas":  ["75201", "75204", "75206"],
    "Miami":   ["33101", "33125", "33130"],
}

SEGMENTS = ["entry_level", "mid_tier", "premium"]

# Base list price ranges per segment (min, max) in dollars
BASE_PRICES = {
    "entry_level": (220_000, 310_000),
    "mid_tier":    (380_000, 520_000),
    "premium":     (650_000, 950_000),
}

# Normal offer-vs-market offset: Opendoor typically offers 0-2% below market
NORMAL_OFFER_DISCOUNT = -0.01  # -1% on average

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _jitter(value: float, pct: float = 0.03) -> float:
    """Add ±pct% random noise to value."""
    return value * (1 + random.uniform(-pct, pct))


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _week_start(base_date: date, week_num: int) -> date:
    """Return Monday of the given week offset from base_date."""
    return base_date + timedelta(weeks=week_num - 1)


# ---------------------------------------------------------------------------
# Per-row generators with story injection
# ---------------------------------------------------------------------------

def _generate_row(
    week: int,
    week_start_date: date,
    market: str,
    zip_code: str,
    segment: str,
) -> dict:
    """
    Generate a single synthetic data row.

    Stories injected:
      - Phoenix mid_tier  wk≥8: offer price drifts 4-6% above market
      - Atlanta           wk≥6: DOM increases progressively
      - Dallas            wk≥7: lead→offer rate falls 3%/wk, close rate softens
      - Miami             all:  healthy baseline
    """

    # --- Base prices ---
    price_lo, price_hi = BASE_PRICES[segment]
    list_price = round(random.uniform(price_lo, price_hi), -3)  # round to $1k
    market_estimated_value = round(_jitter(list_price, 0.04), -3)

    # --- Offer price: normally 0-2% below market ---
    offer_discount = NORMAL_OFFER_DISCOUNT + random.uniform(-0.01, 0.01)

    # Story 1: Phoenix mid_tier pricing misalignment (wk >= 8)
    is_phoenix_mid_misaligned = (
        market == "Phoenix" and segment == "mid_tier" and week >= 8
    )
    if is_phoenix_mid_misaligned:
        # Drift to 4-6% ABOVE market, growing slightly each week
        drift_weeks = week - 7  # 1 at wk8, 2 at wk9, …
        drift_magnitude = 0.04 + min(drift_weeks * 0.004, 0.02)  # 4% → 6%
        offer_discount = drift_magnitude + random.uniform(-0.005, 0.005)

    opendoor_offer_price = round(market_estimated_value * (1 + offer_discount), -3)

    # --- Acceptance rate ---
    # Baseline acceptance rate depends on segment (premium harder to close)
    base_accept = {"entry_level": 0.68, "mid_tier": 0.72, "premium": 0.60}[segment]

    if is_phoenix_mid_misaligned:
        # Drop ~12% total over the period: steeper initial drop then continued decline
        # Week 8: -6pp, Week 9: -9pp, Week 10: -11pp, Week 11: -12pp, Week 12: -13pp
        drop_weeks = week - 7
        accept_rate = base_accept - (0.04 * drop_weeks) + random.uniform(-0.01, 0.01)
        accept_rate = _clamp(accept_rate, 0.35, base_accept)
    else:
        accept_rate = _jitter(base_accept, 0.04)

    # --- Lead / offer / close funnel ---
    base_leads = {"entry_level": 55, "mid_tier": 40, "premium": 22}[segment]
    base_lead_to_offer = 0.58  # 58% of leads produce an offer
    base_offer_to_close = 0.75

    # Story 3: Dallas funnel deterioration (wk >= 7)
    if market == "Dallas" and week >= 7:
        drop_weeks = week - 6  # 1 at wk7
        lead_to_offer_rate = base_lead_to_offer - (0.03 * drop_weeks) + random.uniform(-0.01, 0.01)
        lead_to_offer_rate = _clamp(lead_to_offer_rate, 0.25, base_lead_to_offer)
        offer_to_close_rate = base_offer_to_close - (0.01 * drop_weeks) + random.uniform(-0.005, 0.005)
        offer_to_close_rate = _clamp(offer_to_close_rate, 0.55, base_offer_to_close)
    else:
        lead_to_offer_rate = base_lead_to_offer + random.uniform(-0.03, 0.03)
        offer_to_close_rate = base_offer_to_close + random.uniform(-0.02, 0.02)

    lead_count = max(5, int(base_leads + random.gauss(0, 5)))
    offer_count = max(1, int(lead_count * lead_to_offer_rate))
    accepted_offer_count = max(0, int(offer_count * accept_rate))
    close_count = max(0, int(accepted_offer_count * offer_to_close_rate))

    # --- Days to accept (seller side) ---
    base_days_to_accept = {"entry_level": 3.5, "mid_tier": 5.0, "premium": 8.0}[segment]
    if is_phoenix_mid_misaligned:
        # Sellers taking longer as price seems off
        days_to_accept = round(_jitter(base_days_to_accept * 1.2, 0.1), 1)
    else:
        days_to_accept = round(_jitter(base_days_to_accept, 0.15), 1)

    seller_accepted = accepted_offer_count > 0

    # --- Inventory metrics ---
    base_dom = {"entry_level": 22, "mid_tier": 28, "premium": 42}[segment]
    base_inv_count = {"entry_level": 80, "mid_tier": 55, "premium": 30}[segment]

    # Story 2: Atlanta inventory aging (wk >= 6)
    if market == "Atlanta" and week >= 6:
        age_weeks = week - 5  # 1 at wk6
        # DOM increases ~4 days per week of aging — enough to push above detection threshold
        inventory_dom = round(base_dom + (4.5 * age_weeks) + random.gauss(0, 1.0), 1)
        inventory_dom = _clamp(inventory_dom, base_dom, base_dom + 60)
    else:
        inventory_dom = round(_jitter(base_dom, 0.08), 1)

    inventory_count = max(10, int(_jitter(base_inv_count, 0.10)))

    # --- Margin estimates ---
    # Acquisition margin: what Opendoor expects to make on purchase
    base_acq_margin = {"entry_level": 0.045, "mid_tier": 0.038, "premium": 0.032}[segment]
    # Resale margin: realized on resale
    base_resale_margin = {"entry_level": 0.062, "mid_tier": 0.054, "premium": 0.041}[segment]

    # Phoenix misalignment compresses acquisition margin (overpaying)
    if is_phoenix_mid_misaligned:
        acq_margin = base_acq_margin - (0.005 * (week - 7)) + random.uniform(-0.003, 0.003)
        acq_margin = _clamp(acq_margin, 0.005, base_acq_margin)
    else:
        acq_margin = _jitter(base_acq_margin, 0.08)

    resale_margin = _jitter(base_resale_margin, 0.08)

    return {
        "week": week,
        "week_start": week_start_date.isoformat(),
        "market": market,
        "zip_code": zip_code,
        "home_segment": segment,
        "list_price": list_price,
        "opendoor_offer_price": opendoor_offer_price,
        "market_estimated_value": market_estimated_value,
        "seller_accepted_offer": seller_accepted,
        "days_to_accept": days_to_accept,
        "lead_count": lead_count,
        "offer_count": offer_count,
        "accepted_offer_count": accepted_offer_count,
        "close_count": close_count,
        "inventory_days_on_market": inventory_dom,
        "inventory_count": inventory_count,
        "acquisition_margin_estimate": round(acq_margin, 4),
        "resale_margin_estimate": round(resale_margin, 4),
    }


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_data() -> pd.DataFrame:
    """
    Generate 12 weeks of synthetic Opendoor market data.

    Returns a pandas DataFrame with one row per
    (week, market, zip_code, home_segment) combination.

    Shape: 12 weeks × 4 markets × 3 zips × 3 segments = 432 rows.
    """
    random.seed(42)  # ensure reproducibility when called as a function

    base_date = date(2024, 10, 7)  # Week 1 starts on a Monday
    rows = []

    for week in range(1, 13):
        ws = _week_start(base_date, week)
        for market in MARKETS:
            for zip_code in ZIP_CODES[market]:
                for segment in SEGMENTS:
                    row = _generate_row(week, ws, market, zip_code, segment)
                    rows.append(row)

    df = pd.DataFrame(rows)

    # Ensure correct dtypes
    df["week_start"] = pd.to_datetime(df["week_start"])
    df["seller_accepted_offer"] = df["seller_accepted_offer"].astype(bool)

    return df


# ---------------------------------------------------------------------------
# Standalone execution — write CSV to output/
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    df = generate_data()

    # Resolve output path relative to repo root, not cwd
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, "..", "output")
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "synthetic_data.csv")

    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} rows → {out_path}")
    print(df.groupby(["market", "home_segment"])["week"].count().to_string())
