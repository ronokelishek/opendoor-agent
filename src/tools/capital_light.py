"""
Capital-Light Intelligence Layer
=================================
Opendoor 2026 strategy: maximize Contribution Margin and Inventory Turn.
Not "how many homes can we buy" — "which homes return the most per dollar deployed, fastest."

Three tools:
  get_contribution_margin_forecast()  — CM per deal after all costs
  detect_inventory_surges()           — Z-score surge detector, market-level
  rank_top_100_deals()                — ROI + CM + turn velocity composite score

Semantic Layer:
  SEMANTIC_FILTERS — translates natural language queries into structured filters
"""

import random
import statistics
from src.tools.data_loader import load_market_data

# ── SEMANTIC LAYER ────────────────────────────────────────────────────────────
# Translates natural language concepts → structured filter criteria
# Lets the agent interpret business intent, not just raw metrics

SEMANTIC_FILTERS = {
    "high-risk markets": {
        "days_on_market_gt": 45,
        "price_drop_pct_gt": 2.0,
        "months_supply_gt": 4.0,
        "description": "Markets where holding costs are rising and exit timing is uncertain",
    },
    "capital-light opportunities": {
        "total_capital_lt": 350000,
        "roi_pct_gt": 12.0,
        "days_on_market_lt": 55,
        "description": "Deals that deploy less capital and turn faster — optimized for inventory velocity",
    },
    "high contribution margin": {
        "contribution_margin_gt": 40000,
        "cm_pct_gt": 10.0,
        "description": "Deals where net margin after all costs exceeds CM floor threshold",
    },
    "inventory surge": {
        "inventory_z_score_gt": 1.5,
        "description": "Markets where inventory is building abnormally fast — demand destruction signal",
    },
    "fast turn deals": {
        "expected_hold_days_lt": 75,
        "dom_lt": 50,
        "description": "Deals in liquid markets with strong absorption — minimize days in possession",
    },
    "distressed acquisition": {
        "asking_discount_pct_gt": 15,
        "condition": ["moderate", "full_gut"],
        "description": "Properties priced significantly below market value due to condition",
    },
}

# ── CONSTANTS ─────────────────────────────────────────────────────────────────
OPENDOOR_SERVICE_FEE = 0.055       # ~5.5% charged to seller
HOLDING_COST_PER_DAY_PCT = 0.00025 # ~9% annualized carrying cost
SELLING_COST_PCT = 0.06            # agent + closing + transfer
TARGET_HOLD_DAYS = 90              # Opendoor 2026 target: reduce days in possession
CM_FLOOR = 30000                   # minimum acceptable contribution margin per deal

RENO_TIERS = {
    "cosmetic":  {"cost_per_sqft": (12, 22), "arv_mult": 1.12, "hold_days_add": 15},
    "moderate":  {"cost_per_sqft": (28, 45), "arv_mult": 1.25, "hold_days_add": 35},
    "full_gut":  {"cost_per_sqft": (55, 90), "arv_mult": 1.42, "hold_days_add": 65},
}

MARKET_STREETS = {
    "Phoenix":   ["Camelback Rd", "McDowell Rd", "Indian School Rd", "Glendale Ave", "Bethany Home Rd"],
    "Atlanta":   ["Peachtree St", "Ponce de Leon Ave", "Piedmont Ave", "Moreland Ave", "Howell Mill Rd"],
    "Dallas":    ["Mockingbird Ln", "Lovers Ln", "Greenville Ave", "Henderson Ave", "Ross Ave"],
    "Charlotte": ["Providence Rd", "Monroe Rd", "Independence Blvd", "Central Ave", "Woodlawn Rd"],
}


# ── DEAL GENERATOR (shared) ───────────────────────────────────────────────────

def _build_deal_universe(seed: int = 42) -> list:
    """Generate 100 realistic deals with full CM and velocity metrics."""
    rng = random.Random(seed)
    df = load_market_data()
    latest = df.sort_values("date").groupby("market").last().reset_index()

    deals = []
    deal_id = 1

    for _, row in latest.iterrows():
        market = row["market"]
        median_price = row["median_sale_price"]
        market_dom = int(row["days_on_market"])
        ppsf_market = float(row["price_per_sqft"])
        streets = MARKET_STREETS.get(market, ["Main St"])

        for _ in range(25):
            sqft = rng.randint(1100, 3200)
            beds = rng.choices([3, 4, 5], weights=[55, 35, 10])[0]
            baths = rng.choice([2, 2, 2.5, 3])
            condition = rng.choices(
                ["cosmetic", "moderate", "full_gut"], weights=[50, 35, 15]
            )[0]

            tier = RENO_TIERS[condition]

            # Full market value based on sqft × market price/sqft
            ppsf = ppsf_market * rng.uniform(0.88, 1.12)
            full_market_value = round(ppsf * sqft / 1000) * 1000

            # Distressed discount by condition
            condition_discount = {"cosmetic": 0.94, "moderate": 0.84, "full_gut": 0.72}
            asking_price = round(full_market_value * condition_discount[condition] / 1000) * 1000
            asking_discount_pct = round((1 - condition_discount[condition]) * 100, 1)

            # DOM negotiation discount
            dom_discount = min(0.06, max(0, (market_dom - 30) * 0.0015))
            acquisition_price = round(asking_price * (1 - dom_discount))

            # Renovation
            reno_rate = rng.uniform(*tier["cost_per_sqft"])
            reno_cost = round(sqft * reno_rate / 1000) * 1000

            # ARV (applied to full market value, not buy price)
            arv = round(full_market_value * tier["arv_mult"] / 1000) * 1000

            # Hold days = market DOM + reno time
            prop_dom = max(1, market_dom + rng.randint(-10, 20))
            reno_hold_days = tier["hold_days_add"] + rng.randint(-5, 10)
            total_hold_days = prop_dom + reno_hold_days

            # Cost stack
            holding_cost = round(acquisition_price * HOLDING_COST_PER_DAY_PCT * total_hold_days)
            selling_cost = round(arv * SELLING_COST_PCT)
            total_cost = acquisition_price + reno_cost + holding_cost + selling_cost

            # Contribution Margin = what Opendoor actually keeps
            gross_revenue = arv
            contribution_margin = gross_revenue - total_cost
            cm_pct = round(contribution_margin / arv * 100, 1) if arv > 0 else 0

            # ROI on deployed capital
            total_capital = acquisition_price + reno_cost
            roi_pct = round(contribution_margin / total_capital * 100, 1) if total_capital > 0 else 0

            # Inventory turn score: higher is better (CM per day held)
            cm_per_day = round(contribution_margin / total_hold_days, 0) if total_hold_days > 0 else 0

            # Composite score: balances ROI, CM, and velocity (capital-light lens)
            velocity_bonus = max(0, (TARGET_HOLD_DAYS - total_hold_days) * 0.1)
            composite_score = round(roi_pct + velocity_bonus, 1)

            deals.append({
                "deal_id": f"OD-{deal_id:03d}",
                "market": market,
                "address": f"{rng.randint(100, 9999)} {rng.choice(streets)}",
                "beds": beds,
                "baths": baths,
                "sqft": sqft,
                "condition": condition,
                "asking_price": asking_price,
                "asking_discount_pct": asking_discount_pct,
                "acquisition_price": acquisition_price,
                "reno_cost": reno_cost,
                "arv": arv,
                "holding_cost": holding_cost,
                "selling_cost": selling_cost,
                "total_cost": total_cost,
                "contribution_margin": contribution_margin,
                "cm_pct": cm_pct,
                "total_capital_required": total_capital,
                "roi_pct": roi_pct,
                "total_hold_days": total_hold_days,
                "cm_per_day": cm_per_day,
                "composite_score": composite_score,
                "meets_cm_floor": contribution_margin >= CM_FLOOR,
            })
            deal_id += 1

    return deals


# ── TOOL 1: CONTRIBUTION MARGIN FORECAST ─────────────────────────────────────

def get_contribution_margin_forecast(
    market: str = None,
    condition: str = None,
    max_capital: int = None,
    min_cm: int = None,
) -> dict:
    """
    Forecast contribution margin for deals.
    CM = ARV - acquisition - reno - holding costs - selling costs.
    This is the metric Opendoor investors actually care about.
    """
    deals = _build_deal_universe()

    if market:
        deals = [d for d in deals if d["market"].lower() == market.lower()]
    if condition:
        deals = [d for d in deals if d["condition"] == condition]
    if max_capital:
        deals = [d for d in deals if d["total_capital_required"] <= max_capital]
    if min_cm:
        deals = [d for d in deals if d["contribution_margin"] >= min_cm]

    deals = [d for d in deals if d["contribution_margin"] > 0]
    deals.sort(key=lambda x: x["contribution_margin"], reverse=True)

    total_cm = sum(d["contribution_margin"] for d in deals)
    total_capital = sum(d["total_capital_required"] for d in deals)
    avg_cm_pct = round(statistics.mean(d["cm_pct"] for d in deals), 1) if deals else 0
    avg_hold = round(statistics.mean(d["total_hold_days"] for d in deals)) if deals else 0
    below_floor = sum(1 for d in deals if not d["meets_cm_floor"])

    return {
        "tool": "get_contribution_margin_forecast",
        "filters": {"market": market, "condition": condition, "max_capital": max_capital, "min_cm": min_cm},
        "portfolio_summary": {
            "deal_count": len(deals),
            "total_contribution_margin": total_cm,
            "total_capital_required": total_capital,
            "avg_cm_pct": avg_cm_pct,
            "avg_hold_days": avg_hold,
            "deals_below_cm_floor": below_floor,
            "cm_floor_threshold": CM_FLOOR,
        },
        "top_deals": deals[:10],
    }


# ── TOOL 2: INVENTORY SURGE DETECTOR ─────────────────────────────────────────

def detect_inventory_surges(threshold_z: float = 1.5) -> dict:
    """
    Z-score based inventory surge detector.
    Flags markets where inventory is building abnormally fast.
    A surge = demand destruction signal = rising hold times = CM compression.
    Triggers the proactive monitoring loop.
    """
    df = load_market_data()
    surges = []
    market_snapshots = []

    for market in df["market"].unique():
        mdf = df[df["market"] == market].sort_values("date")
        inv_series = mdf["inventory"].tolist()
        dates = mdf["date"].dt.strftime("%Y-%m").tolist()

        mean_inv = statistics.mean(inv_series)
        std_inv = statistics.stdev(inv_series) if len(inv_series) > 1 else 1
        latest_inv = inv_series[-1]
        z_score = round((latest_inv - mean_inv) / std_inv, 2)

        # MoM inventory change
        mom_change_pct = round((inv_series[-1] - inv_series[-2]) / inv_series[-2] * 100, 1) if len(inv_series) >= 2 else 0

        # Estimate CM impact: more inventory = longer hold = higher holding cost
        latest_price = int(mdf["median_sale_price"].iloc[-1])
        extra_hold_days = max(0, int(z_score * 10)) if z_score > 0 else 0
        cm_at_risk_per_deal = round(latest_price * HOLDING_COST_PER_DAY_PCT * extra_hold_days)

        snapshot = {
            "market": market,
            "latest_inventory": int(latest_inv),
            "avg_inventory": round(mean_inv),
            "inventory_z_score": z_score,
            "mom_change_pct": mom_change_pct,
            "is_surge": z_score >= threshold_z,
            "extra_hold_days_estimated": extra_hold_days,
            "cm_at_risk_per_deal": cm_at_risk_per_deal,
            "trend": "surging" if z_score >= threshold_z else "elevated" if z_score >= 1.0 else "normal",
        }
        market_snapshots.append(snapshot)
        if z_score >= threshold_z:
            surges.append(snapshot)

    surges.sort(key=lambda x: x["inventory_z_score"], reverse=True)
    market_snapshots.sort(key=lambda x: x["inventory_z_score"], reverse=True)

    return {
        "tool": "detect_inventory_surges",
        "threshold_z": threshold_z,
        "surge_count": len(surges),
        "triggered": len(surges) > 0,
        "surging_markets": surges,
        "all_markets": market_snapshots,
        "recommendation": (
            "ALERT: Inventory surging in one or more markets. "
            "Automatically triggering deal ranking to identify capital-light exits."
            if surges else
            "No inventory surges detected. Market absorption is within normal range."
        ),
    }


# ── TOOL 3: RANK TOP 100 DEALS (CAPITAL-LIGHT COMPOSITE) ─────────────────────

def rank_top_100_deals(
    market: str = None,
    max_capital: int = None,
    min_cm: int = None,
    min_roi: float = None,
    max_hold_days: int = None,
    semantic_filter: str = None,
) -> dict:
    """
    Rank deals by composite score = ROI + velocity bonus.
    Prioritizes Contribution Margin AND Inventory Turn — Opendoor 2026 strategy.
    Optionally apply a semantic filter (e.g. 'capital-light opportunities').
    """
    # Apply semantic filter if provided
    applied_semantic = None
    if semantic_filter and semantic_filter in SEMANTIC_FILTERS:
        sf = SEMANTIC_FILTERS[semantic_filter]
        applied_semantic = sf
        # Map semantic filter fields to hard filters
        if "total_capital_lt" in sf and max_capital is None:
            max_capital = sf["total_capital_lt"]
        if "roi_pct_gt" in sf and min_roi is None:
            min_roi = sf["roi_pct_gt"]
        if "contribution_margin_gt" in sf and min_cm is None:
            min_cm = sf["contribution_margin_gt"]
        if "expected_hold_days_lt" in sf and max_hold_days is None:
            max_hold_days = sf["expected_hold_days_lt"]

    deals = _build_deal_universe()

    if market:
        deals = [d for d in deals if d["market"].lower() == market.lower()]
    if max_capital:
        deals = [d for d in deals if d["total_capital_required"] <= max_capital]
    if min_cm:
        deals = [d for d in deals if d["contribution_margin"] >= min_cm]
    if min_roi:
        deals = [d for d in deals if d["roi_pct"] >= min_roi]
    if max_hold_days:
        deals = [d for d in deals if d["total_hold_days"] <= max_hold_days]

    deals = [d for d in deals if d["contribution_margin"] > 0]
    deals.sort(key=lambda x: x["composite_score"], reverse=True)
    deals = deals[:100]

    total_cm = sum(d["contribution_margin"] for d in deals)
    total_capital = sum(d["total_capital_required"] for d in deals)
    avg_hold = round(statistics.mean(d["total_hold_days"] for d in deals)) if deals else 0
    avg_cm_per_day = round(statistics.mean(d["cm_per_day"] for d in deals)) if deals else 0

    by_market = {}
    for d in deals:
        m = d["market"]
        if m not in by_market:
            by_market[m] = {"count": 0, "total_cm": 0, "avg_roi": []}
        by_market[m]["count"] += 1
        by_market[m]["total_cm"] += d["contribution_margin"]
        by_market[m]["avg_roi"].append(d["roi_pct"])
    for m in by_market:
        by_market[m]["avg_roi_pct"] = round(statistics.mean(by_market[m]["avg_roi"]), 1)
        del by_market[m]["avg_roi"]

    return {
        "tool": "rank_top_100_deals",
        "semantic_filter_applied": applied_semantic,
        "filters": {
            "market": market,
            "max_capital": max_capital,
            "min_cm": min_cm,
            "min_roi": min_roi,
            "max_hold_days": max_hold_days,
        },
        "portfolio_summary": {
            "deals_returned": len(deals),
            "total_contribution_margin": total_cm,
            "total_capital_required": total_capital,
            "avg_hold_days": avg_hold,
            "avg_cm_per_day": avg_cm_per_day,
            "capital_efficiency": round(total_cm / total_capital * 100, 1) if total_capital else 0,
        },
        "by_market": by_market,
        "deals": deals,
    }
