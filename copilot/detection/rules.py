"""
detection/rules.py
------------------
Deterministic issue detection logic. No LLM involved — pure Python rules
applied to the computed metrics DataFrame.

Design principles:
  - Each detector is self-contained and independently testable
  - All thresholds come from metrics/definitions.ISSUE_THRESHOLDS (single source of truth)
  - Detectors look at the most recent 2 weeks to require persistence, not noise
  - Evidence bullets are written in business memo language, not code

Detection rules:
  detect_pricing_misalignment  — offer % above market AND acceptance rate drop
  detect_inventory_aging       — aging rate threshold OR sustained DOM increase
  detect_funnel_deterioration  — lead-to-offer OR offer-to-close WoW drops
  detect_margin_compression    — acquisition margin WoW drop
"""

import uuid
from typing import List

import pandas as pd

from detection.issue_types import Issue, assign_severity
from metrics.definitions import ISSUE_THRESHOLDS

# ---------------------------------------------------------------------------
# Threshold aliases (for readability)
# ---------------------------------------------------------------------------

T = ISSUE_THRESHOLDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _latest_two_weeks(
    metrics_df: pd.DataFrame,
    market: str,
    segment: str,
) -> tuple[pd.Series | None, pd.Series | None]:
    """
    Return (current_week_row, prior_week_row) for a given market/segment.
    Returns (None, None) if fewer than 2 data points exist.
    """
    subset = metrics_df[
        (metrics_df["market"] == market) &
        (metrics_df["home_segment"] == segment)
    ].sort_values("week_start")

    if len(subset) < 2:
        return None, None

    return subset.iloc[-1], subset.iloc[-2]


def _baseline_avg(
    metrics_df: pd.DataFrame,
    market: str,
    segment: str,
    metric: str,
    baseline_weeks: int = 4,
) -> float | None:
    """
    Compute the average of a metric over the earliest N weeks for a given
    market/segment — used as a pre-issue baseline for trend detection.

    Returns None if insufficient data.
    """
    subset = metrics_df[
        (metrics_df["market"] == market) &
        (metrics_df["home_segment"] == segment)
    ].sort_values("week_start")

    if len(subset) < baseline_weeks + 1:
        return None

    baseline = subset.head(baseline_weeks)[metric].dropna()
    if baseline.empty:
        return None
    return float(baseline.mean())


def _fmt_pct(value: float) -> str:
    """Format a ratio as a percentage string."""
    return f"{value * 100:.1f}%"


def _fmt_pct_pp(value: float) -> str:
    """Format a ratio delta as percentage points."""
    sign = "+" if value >= 0 else ""
    return f"{sign}{value * 100:.1f}pp"


def _make_issue_id(issue_type: str, market: str, segment: str, week_start: str) -> str:
    return f"{issue_type}_{market}_{segment}_{week_start}".replace(" ", "_")


# ---------------------------------------------------------------------------
# Individual detectors
# ---------------------------------------------------------------------------

def detect_pricing_misalignment(metrics_df: pd.DataFrame) -> List[Issue]:
    """
    Flag markets/segments where Opendoor's offer price is materially above
    market estimated value AND acceptance rates are falling.

    Fires when:
      avg_offer_vs_market_pct > PRICING_OFFER_VS_MARKET_WARN (2%)
      AND offer_acceptance_rate WoW drop > PRICING_ACCEPTANCE_DROP_WARN (5%)
    """
    issues = []

    for market in metrics_df["market"].unique():
        for segment in metrics_df["home_segment"].unique():
            curr, prev = _latest_two_weeks(metrics_df, market, segment)
            if curr is None:
                continue

            offer_vs_market = curr.get("avg_offer_vs_market_pct", 0.0) or 0.0
            acceptance_now = curr.get("offer_acceptance_rate") or 0.0
            acceptance_prev = prev.get("offer_acceptance_rate") or 0.0
            acceptance_drop = acceptance_prev - acceptance_now  # positive = worsened

            wow_col = "offer_acceptance_rate_wow_delta"
            acceptance_wow = -(curr.get(wow_col, 0.0) or 0.0)  # flip sign: positive = drop

            # Compute cumulative acceptance drop vs baseline (first 4 weeks)
            baseline_acceptance = _baseline_avg(
                metrics_df, market, segment, "offer_acceptance_rate", baseline_weeks=4
            )
            cumulative_drop = 0.0
            if baseline_acceptance is not None:
                cumulative_drop = baseline_acceptance - acceptance_now  # positive = worsened

            # Both conditions must be true:
            #   1. Offer price materially above market
            #   2. Acceptance rate fell (WoW OR vs baseline)
            price_flag = offer_vs_market > T["PRICING_OFFER_VS_MARKET_WARN"]
            acceptance_flag = (
                acceptance_drop > T["PRICING_ACCEPTANCE_DROP_WARN"]  # WoW drop
                or cumulative_drop > T["PRICING_ACCEPTANCE_DROP_WARN"] * 2  # Cumulative drop vs baseline
            )

            if not (price_flag and acceptance_flag):
                continue

            # Use the larger of WoW and cumulative drop for evidence
            effective_drop = max(acceptance_drop, cumulative_drop)

            # Assign severity based on offer vs market deviation
            severity = assign_severity(
                offer_vs_market,
                warn=T["PRICING_OFFER_VS_MARKET_WARN"],
                critical=T["PRICING_OFFER_VS_MARKET_CRITICAL"],
            )
            # Escalate if acceptance drop is also critical
            if acceptance_drop > T["PRICING_ACCEPTANCE_DROP_CRITICAL"]:
                severity = "critical"

            confidence = "High" if offer_vs_market > T["PRICING_OFFER_VS_MARKET_CRITICAL"] else "Medium-High"

            evidence = [
                (
                    f"Opendoor offer price is averaging {_fmt_pct(offer_vs_market)} above "
                    f"market estimated value this week (warn threshold: "
                    f"{_fmt_pct(T['PRICING_OFFER_VS_MARKET_WARN'])})."
                ),
                (
                    f"Seller acceptance rate fell {_fmt_pct(acceptance_drop)} WoW "
                    f"to {_fmt_pct(acceptance_now)} "
                    f"(prior week: {_fmt_pct(acceptance_prev)})."
                    + (
                        f" Cumulative decline from 4-week baseline: "
                        f"{_fmt_pct(cumulative_drop)} ({_fmt_pct(baseline_acceptance or 0)} → {_fmt_pct(acceptance_now)})."
                        if baseline_acceptance and cumulative_drop > acceptance_drop
                        else ""
                    )
                ),
                (
                    f"This combination — above-market offers paired with declining "
                    f"acceptance — indicates sellers are rejecting inflated offers "
                    f"or the pricing model is overvaluing this segment."
                ),
            ]

            # Add acquisition margin context if available
            acq_margin = curr.get("avg_acquisition_margin")
            if acq_margin is not None:
                evidence.append(
                    f"Estimated acquisition margin is {_fmt_pct(acq_margin)}, "
                    f"reflecting the cost of above-market acquisition pricing."
                )

            issues.append(Issue(
                issue_id=_make_issue_id("PRICING_MISALIGNMENT", market, segment, str(curr["week_start"])[:10]),
                issue_type="PRICING_MISALIGNMENT",
                market=market,
                segment=segment,
                severity=severity,
                week_start=str(curr["week_start"])[:10],
                title=f"Pricing Misalignment — {market} {segment.replace('_', ' ').title()}",
                evidence=evidence,
                metrics_snapshot={
                    "avg_offer_vs_market_pct": round(offer_vs_market, 4),
                    "offer_acceptance_rate": round(acceptance_now, 4),
                    "avg_acquisition_margin": round(acq_margin, 4) if acq_margin else None,
                    "offer_count": int(curr.get("offer_count", 0)),
                    "accepted_offer_count": int(curr.get("accepted_offer_count", 0)),
                },
                wow_deltas={
                    "offer_acceptance_rate_wow_delta": round(curr.get("offer_acceptance_rate_wow_delta", 0) or 0, 4),
                    "avg_offer_vs_market_pct_wow_delta": round(curr.get("avg_offer_vs_market_pct_wow_delta", 0) or 0, 4),
                    "avg_acquisition_margin_wow_delta": round(curr.get("avg_acquisition_margin_wow_delta", 0) or 0, 4),
                },
                confidence=confidence,
            ))

    return issues


def detect_inventory_aging(metrics_df: pd.DataFrame) -> List[Issue]:
    """
    Flag markets where aging inventory is rising toward problematic levels.

    Fires when:
      aging_inventory_rate > AGING_RATE_WARN (15%)
      OR avg_days_on_market WoW increase > AGING_DOM_INCREASE_WARN (5 days)
         for 2+ consecutive weeks
    """
    issues = []

    for market in metrics_df["market"].unique():
        # Inventory aging is evaluated at the market level (not per segment)
        # since inventory is a market-wide supply signal. We use aggregate
        # across segments but report on the most-affected segment.
        for segment in metrics_df["home_segment"].unique():
            curr, prev = _latest_two_weeks(metrics_df, market, segment)
            if curr is None:
                continue

            aging_rate = curr.get("aging_inventory_rate", 0.0) or 0.0
            avg_dom = curr.get("avg_days_on_market", 0.0) or 0.0
            dom_wow = curr.get("avg_days_on_market_wow_delta", 0.0) or 0.0
            dom_wow_prev = prev.get("avg_days_on_market_wow_delta", 0.0) if prev is not None else 0.0
            dom_wow_prev = dom_wow_prev or 0.0

            # Cumulative DOM increase vs baseline
            baseline_dom = _baseline_avg(metrics_df, market, segment, "avg_days_on_market", baseline_weeks=4)
            cumulative_dom_increase = (avg_dom - baseline_dom) if baseline_dom else 0.0

            # Condition A: Aging rate threshold breached
            cond_a = aging_rate > T["AGING_RATE_WARN"]

            # Condition B: DOM increasing > threshold WoW for 2+ consecutive weeks
            cond_b = (
                dom_wow > T["AGING_DOM_INCREASE_WARN"] and
                dom_wow_prev > 0  # was already increasing last week
            )

            # Condition C: Sustained cumulative DOM increase > 2x the weekly threshold
            cond_c = cumulative_dom_increase > T["AGING_DOM_INCREASE_WARN"] * 2

            if not (cond_a or cond_b or cond_c):
                continue

            severity = assign_severity(
                aging_rate,
                warn=T["AGING_RATE_WARN"],
                critical=T["AGING_RATE_CRITICAL"],
            )
            # If DOM is rising fast or cumulative trend is large, at minimum medium
            if (cond_b or cond_c) and severity == "low":
                severity = "medium"
            # Cumulative increase of 3x threshold → high
            if cumulative_dom_increase > T["AGING_DOM_INCREASE_WARN"] * 3 and severity in ["low", "medium"]:
                severity = "high"

            confidence = "High" if (cond_a and (cond_b or cond_c)) else "Medium-High" if (cond_a or cond_c) else "Medium"

            evidence = []
            if cond_a:
                evidence.append(
                    f"Estimated aging inventory rate is {_fmt_pct(aging_rate)} "
                    f"(threshold: {_fmt_pct(T['AGING_RATE_WARN'])}). "
                    f"Approximately {_fmt_pct(aging_rate)} of active inventory "
                    f"has been listed for more than {T['AGING_DOM_THRESHOLD_DAYS']} days."
                )
            if cond_b:
                evidence.append(
                    f"Average days-on-market increased {dom_wow:.1f} days WoW "
                    f"(threshold: {T['AGING_DOM_INCREASE_WARN']} days) "
                    f"and was also rising last week (+{dom_wow_prev:.1f} days), "
                    f"confirming a multi-week trend."
                )
            if cond_c and baseline_dom:
                evidence.append(
                    f"Cumulative DOM increase vs 4-week baseline: "
                    f"+{cumulative_dom_increase:.1f} days ({baseline_dom:.1f} → {avg_dom:.1f}), "
                    f"confirming a sustained deterioration trend."
                )
            evidence.append(
                f"Current average DOM is {avg_dom:.1f} days for {market} {segment.replace('_', ' ')}. "
                f"Sustained DOM growth signals reduced buyer demand or overpriced resale listings."
            )
            evidence.append(
                "Aged inventory typically requires price reductions of 3-8% to clear, "
                "directly compressing resale margins."
            )

            issues.append(Issue(
                issue_id=_make_issue_id("INVENTORY_AGING", market, segment, str(curr["week_start"])[:10]),
                issue_type="INVENTORY_AGING",
                market=market,
                segment=segment,
                severity=severity,
                week_start=str(curr["week_start"])[:10],
                title=f"Inventory Aging — {market} {segment.replace('_', ' ').title()}",
                evidence=evidence,
                metrics_snapshot={
                    "aging_inventory_rate": round(aging_rate, 4),
                    "avg_days_on_market": round(avg_dom, 1),
                    "inventory_count": int(curr.get("inventory_count", 0)),
                    "avg_resale_margin": round(curr.get("avg_resale_margin", 0) or 0, 4),
                },
                wow_deltas={
                    "avg_days_on_market_wow_delta": round(dom_wow, 2),
                    "aging_inventory_rate_wow_delta": round(curr.get("aging_inventory_rate_wow_delta", 0) or 0, 4),
                    "avg_resale_margin_wow_delta": round(curr.get("avg_resale_margin_wow_delta", 0) or 0, 4),
                },
                confidence=confidence,
            ))

    return issues


def detect_funnel_deterioration(metrics_df: pd.DataFrame) -> List[Issue]:
    """
    Flag markets where seller conversion funnel metrics are materially declining.

    Fires when:
      lead_to_offer_rate WoW drop > FUNNEL_L2O_DROP_WARN (3%)
      OR offer_to_close_rate WoW drop > FUNNEL_O2C_DROP_WARN (4%)
    """
    issues = []

    for market in metrics_df["market"].unique():
        for segment in metrics_df["home_segment"].unique():
            curr, prev = _latest_two_weeks(metrics_df, market, segment)
            if curr is None:
                continue

            l2o_now = curr.get("lead_to_offer_rate", 0.0) or 0.0
            l2o_prev = prev.get("lead_to_offer_rate", 0.0) if prev is not None else l2o_now
            l2o_prev = l2o_prev or l2o_now
            l2o_drop = l2o_prev - l2o_now  # positive = worsened

            o2c_now = curr.get("offer_to_close_rate", 0.0) or 0.0
            o2c_prev = prev.get("offer_to_close_rate", 0.0) if prev is not None else o2c_now
            o2c_prev = o2c_prev or o2c_now
            o2c_drop = o2c_prev - o2c_now

            # Cumulative funnel drop vs baseline
            baseline_l2o = _baseline_avg(metrics_df, market, segment, "lead_to_offer_rate", baseline_weeks=4)
            cumulative_l2o_drop = (baseline_l2o - l2o_now) if baseline_l2o else 0.0

            cond_l2o = (
                l2o_drop > T["FUNNEL_L2O_DROP_WARN"]
                or cumulative_l2o_drop > T["FUNNEL_L2O_DROP_WARN"] * 3  # 3+ weeks of drops
            )
            cond_o2c = o2c_drop > T["FUNNEL_O2C_DROP_WARN"]

            if not (cond_l2o or cond_o2c):
                continue

            # Severity based on combined drop magnitude
            max_drop = max(
                l2o_drop / T["FUNNEL_L2O_DROP_WARN"] if cond_l2o else 0,
                o2c_drop / T["FUNNEL_O2C_DROP_WARN"] if cond_o2c else 0,
            )
            if max_drop >= 3:
                severity = "critical"
            elif max_drop >= 2:
                severity = "high"
            elif max_drop >= 1.5:
                severity = "medium"
            else:
                severity = "low"

            confidence = "High" if cond_l2o and cond_o2c else "Medium-High"

            evidence = []
            if cond_l2o:
                evidence.append(
                    f"Lead-to-offer rate fell {_fmt_pct(l2o_drop)} WoW "
                    f"to {_fmt_pct(l2o_now)} "
                    f"(prior week: {_fmt_pct(l2o_prev)}, "
                    f"threshold: {_fmt_pct(T['FUNNEL_L2O_DROP_WARN'])} drop)."
                )
            if cond_o2c:
                evidence.append(
                    f"Offer-to-close rate fell {_fmt_pct(o2c_drop)} WoW "
                    f"to {_fmt_pct(o2c_now)} "
                    f"(prior week: {_fmt_pct(o2c_prev)}, "
                    f"threshold: {_fmt_pct(T['FUNNEL_O2C_DROP_WARN'])} drop)."
                )

            funnel_eff = curr.get("funnel_efficiency", 0.0) or 0.0
            evidence.append(
                f"Overall funnel efficiency (lead → close) is now {_fmt_pct(funnel_eff)}, "
                f"with {int(curr.get('lead_count', 0))} leads generating "
                f"{int(curr.get('close_count', 0))} closes this week."
            )
            evidence.append(
                "Declining lead-to-offer conversion often precedes volume shortfalls "
                "by 2-3 weeks, requiring prompt diagnosis of the friction source."
            )

            issues.append(Issue(
                issue_id=_make_issue_id("FUNNEL_DETERIORATION", market, segment, str(curr["week_start"])[:10]),
                issue_type="FUNNEL_DETERIORATION",
                market=market,
                segment=segment,
                severity=severity,
                week_start=str(curr["week_start"])[:10],
                title=f"Funnel Deterioration — {market} {segment.replace('_', ' ').title()}",
                evidence=evidence,
                metrics_snapshot={
                    "lead_to_offer_rate": round(l2o_now, 4),
                    "offer_to_close_rate": round(o2c_now, 4),
                    "funnel_efficiency": round(funnel_eff, 4),
                    "lead_count": int(curr.get("lead_count", 0)),
                    "offer_count": int(curr.get("offer_count", 0)),
                    "close_count": int(curr.get("close_count", 0)),
                },
                wow_deltas={
                    "lead_to_offer_rate_wow_delta": round(curr.get("lead_to_offer_rate_wow_delta", 0) or 0, 4),
                    "offer_to_close_rate_wow_delta": round(curr.get("offer_to_close_rate_wow_delta", 0) or 0, 4),
                    "funnel_efficiency_wow_delta": round(curr.get("funnel_efficiency_wow_delta", 0) or 0, 4),
                },
                confidence=confidence,
            ))

    return issues


def detect_margin_compression(metrics_df: pd.DataFrame) -> List[Issue]:
    """
    Flag markets where estimated acquisition margins are declining materially.

    Fires when:
      avg_acquisition_margin WoW drop > MARGIN_ACQ_DROP_CRITICAL (2pp)
      OR absolute margin < MARGIN_ACQ_ABS_CRITICAL (2%) and still falling
    """
    issues = []

    for market in metrics_df["market"].unique():
        for segment in metrics_df["home_segment"].unique():
            curr, prev = _latest_two_weeks(metrics_df, market, segment)
            if curr is None:
                continue

            margin_now = curr.get("avg_acquisition_margin", 0.0) or 0.0
            margin_prev = prev.get("avg_acquisition_margin", 0.0) if prev is not None else margin_now
            margin_prev = margin_prev or margin_now
            margin_drop = margin_prev - margin_now  # positive = worsened

            abs_critical = margin_now < T["MARGIN_ACQ_ABS_CRITICAL"]
            drop_critical = margin_drop > T["MARGIN_ACQ_DROP_CRITICAL"]
            drop_warn = margin_drop > T["MARGIN_ACQ_DROP_WARN"]

            if not (drop_critical or (abs_critical and drop_warn)):
                continue

            severity = assign_severity(
                margin_drop,
                warn=T["MARGIN_ACQ_DROP_WARN"],
                critical=T["MARGIN_ACQ_DROP_CRITICAL"],
            )
            if abs_critical:
                severity = "critical"  # Absolute margin <2% is always critical

            confidence = "High" if drop_critical else "Medium-High"

            evidence = [
                (
                    f"Estimated acquisition margin fell {_fmt_pct_pp(margin_drop)} WoW "
                    f"to {_fmt_pct(margin_now)} "
                    f"(prior week: {_fmt_pct(margin_prev)})."
                ),
                (
                    f"Threshold for critical: {_fmt_pct_pp(T['MARGIN_ACQ_DROP_CRITICAL'])} WoW drop "
                    f"or absolute margin below {_fmt_pct(T['MARGIN_ACQ_ABS_CRITICAL'])}."
                ),
            ]
            if abs_critical:
                evidence.append(
                    f"Margin at {_fmt_pct(margin_now)} provides insufficient buffer for "
                    f"holding costs (~1.5%), transaction fees (~1%), and repair contingencies. "
                    f"Continued acquisition at this margin will generate realized losses."
                )
            evidence.append(
                "Margin compression at acquisition typically precedes realized P&L impact "
                "by 60-90 days (the average hold period), creating urgency for recalibration."
            )

            issues.append(Issue(
                issue_id=_make_issue_id("MARGIN_COMPRESSION", market, segment, str(curr["week_start"])[:10]),
                issue_type="MARGIN_COMPRESSION",
                market=market,
                segment=segment,
                severity=severity,
                week_start=str(curr["week_start"])[:10],
                title=f"Margin Compression — {market} {segment.replace('_', ' ').title()}",
                evidence=evidence,
                metrics_snapshot={
                    "avg_acquisition_margin": round(margin_now, 4),
                    "avg_resale_margin": round(curr.get("avg_resale_margin", 0) or 0, 4),
                    "avg_offer_vs_market_pct": round(curr.get("avg_offer_vs_market_pct", 0) or 0, 4),
                },
                wow_deltas={
                    "avg_acquisition_margin_wow_delta": round(curr.get("avg_acquisition_margin_wow_delta", 0) or 0, 4),
                    "avg_resale_margin_wow_delta": round(curr.get("avg_resale_margin_wow_delta", 0) or 0, 4),
                },
                confidence=confidence,
            ))

    return issues


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def detect_all_issues(metrics_df: pd.DataFrame) -> List[Issue]:
    """
    Run all detection rules against the computed metrics DataFrame.

    Args:
        metrics_df: Output of compute_wow_changes(compute_weekly_metrics(df))

    Returns:
        List of Issue objects, sorted by severity (most critical first).
    """
    issues: List[Issue] = []
    issues += detect_pricing_misalignment(metrics_df)
    issues += detect_inventory_aging(metrics_df)
    issues += detect_funnel_deterioration(metrics_df)
    issues += detect_margin_compression(metrics_df)

    # Sort by severity descending, then market alphabetically
    issues.sort(key=lambda i: (-i.severity_rank(), i.market, i.segment))

    return issues
