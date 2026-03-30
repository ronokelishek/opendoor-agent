"""
metrics/calculations.py
-----------------------
Computes all business metrics from the raw synthetic DataFrame.

Key functions:
  compute_weekly_metrics(df)            → one row per (week_start, market, segment)
  compute_wow_changes(metrics_df)       → adds WoW delta columns
  get_market_segment_snapshot(...)      → dict of current + prior week metrics

The aging_inventory_rate approximation:
  Because the raw data stores a single avg DOM per row, we estimate the
  share of aged inventory (>90 days) using a log-normal model:
    If avg DOM = μ and we assume σ ≈ 0.4·μ, we can estimate
    P(X > 90) where X ~ LogNormal(μ, σ).
  This is more realistic than a hard threshold on the mean alone.
"""

import numpy as np
import pandas as pd

from metrics.definitions import ISSUE_THRESHOLDS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AGED_DOM_THRESHOLD = ISSUE_THRESHOLDS["AGING_DOM_THRESHOLD_DAYS"]
DOM_SIGMA_FACTOR = 0.40   # assumed CV of DOM distribution


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Element-wise safe division; returns NaN where denominator is 0."""
    return numerator.div(denominator.replace(0, np.nan))


def _estimate_aging_rate(avg_dom: float) -> float:
    """
    Estimate share of inventory > 90 DOM given average DOM.

    Assumes DOM follows a log-normal distribution with mean=avg_dom
    and σ ≈ 0.4 * avg_dom (a conservative coefficient of variation).

    Returns a float in [0, 1].
    """
    if avg_dom <= 0:
        return 0.0
    mu = avg_dom
    sigma = DOM_SIGMA_FACTOR * avg_dom
    # Log-normal parameters
    sigma_ln = np.sqrt(np.log(1 + (sigma / mu) ** 2))
    mu_ln = np.log(mu) - 0.5 * sigma_ln ** 2
    # P(X > threshold) = 1 - Φ((ln(threshold) - mu_ln) / sigma_ln)
    z = (np.log(AGED_DOM_THRESHOLD) - mu_ln) / sigma_ln
    # Use standard normal CDF approximation
    prob_above = 1 - _normal_cdf(z)
    return float(np.clip(prob_above, 0.0, 1.0))


def _normal_cdf(z: float) -> float:
    """Approximate standard normal CDF using the error function."""
    import math
    return 0.5 * (1 + math.erf(z / np.sqrt(2)))


# ---------------------------------------------------------------------------
# Core metric computation
# ---------------------------------------------------------------------------

def compute_weekly_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate raw row-level data to one row per (week_start, market, home_segment).

    Input columns expected (from synthetic_data.generate_data):
      week_start, market, home_segment, zip_code,
      opendoor_offer_price, market_estimated_value,
      lead_count, offer_count, accepted_offer_count, close_count,
      inventory_days_on_market, inventory_count,
      acquisition_margin_estimate, resale_margin_estimate

    Output adds computed metric columns:
      offer_acceptance_rate, lead_to_offer_rate, offer_to_close_rate,
      avg_offer_vs_market_pct, avg_days_on_market, aging_inventory_rate,
      avg_acquisition_margin, avg_resale_margin, funnel_efficiency
    """
    agg = (
        df.groupby(["week_start", "market", "home_segment"], sort=True)
        .agg(
            week=("week", "first"),
            lead_count=("lead_count", "sum"),
            offer_count=("offer_count", "sum"),
            accepted_offer_count=("accepted_offer_count", "sum"),
            close_count=("close_count", "sum"),
            inventory_count=("inventory_count", "sum"),
            avg_list_price=("list_price", "mean"),
            avg_offer_price=("opendoor_offer_price", "mean"),
            avg_market_value=("market_estimated_value", "mean"),
            avg_days_on_market=("inventory_days_on_market", "mean"),
            avg_acquisition_margin=("acquisition_margin_estimate", "mean"),
            avg_resale_margin=("resale_margin_estimate", "mean"),
        )
        .reset_index()
    )

    # --- Rate metrics ---
    agg["offer_acceptance_rate"] = _safe_div(
        agg["accepted_offer_count"], agg["offer_count"]
    )
    agg["lead_to_offer_rate"] = _safe_div(
        agg["offer_count"], agg["lead_count"]
    )
    agg["offer_to_close_rate"] = _safe_div(
        agg["close_count"], agg["accepted_offer_count"]
    )
    agg["funnel_efficiency"] = _safe_div(
        agg["close_count"], agg["lead_count"]
    )

    # --- Offer vs market ---
    agg["avg_offer_vs_market_pct"] = _safe_div(
        agg["avg_offer_price"] - agg["avg_market_value"],
        agg["avg_market_value"]
    )

    # --- Aging inventory (estimated from avg DOM) ---
    agg["aging_inventory_rate"] = agg["avg_days_on_market"].apply(
        _estimate_aging_rate
    )

    # Sort for consistent downstream ordering
    agg = agg.sort_values(
        ["market", "home_segment", "week_start"]
    ).reset_index(drop=True)

    return agg


# ---------------------------------------------------------------------------
# Week-over-week delta computation
# ---------------------------------------------------------------------------

DELTA_METRICS = [
    "offer_acceptance_rate",
    "lead_to_offer_rate",
    "offer_to_close_rate",
    "avg_offer_vs_market_pct",
    "aging_inventory_rate",
    "avg_days_on_market",
    "avg_acquisition_margin",
    "avg_resale_margin",
    "funnel_efficiency",
]


def compute_wow_changes(metrics_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add WoW (week-over-week) delta columns for all key metrics.

    For each metric M, adds column M_wow_delta = M[t] - M[t-1].
    Deltas are computed within each (market, home_segment) group.

    Returns the enriched DataFrame (does not mutate input).
    """
    df = metrics_df.copy()
    df = df.sort_values(["market", "home_segment", "week_start"])

    for metric in DELTA_METRICS:
        if metric not in df.columns:
            continue
        df[f"{metric}_wow_delta"] = df.groupby(
            ["market", "home_segment"]
        )[metric].diff()

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Snapshot accessor
# ---------------------------------------------------------------------------

def get_market_segment_snapshot(
    metrics_df: pd.DataFrame,
    market: str,
    segment: str,
    week: int | None = None,
) -> dict:
    """
    Return a snapshot dict for a given (market, segment) at the specified week.

    If week is None, uses the most recent week available.

    Returns:
    {
        "market": str,
        "segment": str,
        "week": int,
        "week_start": str,
        "current": {metric: value, ...},
        "prior": {metric: value, ...},
        "deltas": {metric_wow_delta: value, ...},
    }
    """
    subset = metrics_df[
        (metrics_df["market"] == market) &
        (metrics_df["home_segment"] == segment)
    ].sort_values("week_start")

    if subset.empty:
        return {}

    if week is None:
        current_row = subset.iloc[-1]
        prior_row = subset.iloc[-2] if len(subset) >= 2 else None
    else:
        week_subset = subset[subset["week"] == week]
        if week_subset.empty:
            return {}
        current_row = week_subset.iloc[0]
        idx = subset.index.get_loc(current_row.name)
        prior_row = subset.iloc[idx - 1] if idx > 0 else None

    metric_cols = DELTA_METRICS
    delta_cols = [f"{m}_wow_delta" for m in metric_cols if f"{m}_wow_delta" in subset.columns]

    current = {col: current_row[col] for col in metric_cols if col in current_row.index}
    prior = (
        {col: prior_row[col] for col in metric_cols if col in prior_row.index}
        if prior_row is not None
        else {}
    )
    deltas = (
        {col: current_row[col] for col in delta_cols if col in current_row.index}
        if delta_cols
        else {}
    )

    return {
        "market": market,
        "segment": segment,
        "week": int(current_row["week"]),
        "week_start": str(current_row["week_start"])[:10],
        "current": {k: round(float(v), 4) if pd.notna(v) else None for k, v in current.items()},
        "prior": {k: round(float(v), 4) if pd.notna(v) else None for k, v in prior.items()},
        "deltas": {k: round(float(v), 4) if pd.notna(v) else None for k, v in deltas.items()},
    }
