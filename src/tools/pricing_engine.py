"""
Pricing & Conversion Brain
===========================
Opendoor's #1 operational problem: pricing misalignment kills conversion,
and conversion drops kill volume, which kills margin at scale.

Four tools:
  analyze_pricing_accuracy()   — offer vs market deviation by market/segment
  analyze_funnel_drop()        — lead→offer→acceptance→close breakdown
  generate_pricing_actions()   — specific adjustment recommendations with expected impact
  estimate_business_impact()   — translates signals into unit economics ($, homes, margin)

These tools shift the agent from "insight reporter" to "decision engine."
Every output is structured for a Pricing or Operations owner to act on today.
"""

import statistics
from src.tools.data_loader import load_market_data

# ── SEVERITY FRAMEWORK ────────────────────────────────────────────────────────
# Explicit operational tiers — maps directly to response urgency and owner action

SEVERITY_FRAMEWORK = {
    "critical": {
        "label": "CRITICAL",
        "sla": "Immediate — act within 24 hours",
        "examples": ["Pricing misalignment causing confirmed margin loss", "Acceptance rate drop >15% WoW"],
        "owner_action": "Escalate to VP Acquisitions + Pricing Lead. Block new offers until resolved.",
        "color": "red",
    },
    "high": {
        "label": "HIGH",
        "sla": "Act within 24–72 hours",
        "examples": ["LSR below 0.95", "DOM trending up 2+ weeks", "Funnel conversion drop >8% WoW"],
        "owner_action": "Pricing or market-ops owner must produce action plan by next business day.",
        "color": "orange",
    },
    "medium": {
        "label": "MEDIUM",
        "sla": "Monitor and adjust within one week",
        "examples": ["LSR 0.95–0.97", "Inventory building but not yet critical", "Single-week conversion dip"],
        "owner_action": "Flag for weekly review. Adjust if trend continues.",
        "color": "yellow",
    },
    "low": {
        "label": "LOW",
        "sla": "Informational — no immediate action required",
        "examples": ["Slight DOM increase within seasonal norms", "Minor pricing deviation within band"],
        "owner_action": "Log and monitor. Include in next weekly report.",
        "color": "blue",
    },
    "healthy": {
        "label": "HEALTHY",
        "sla": "No action required",
        "examples": ["All signals within benchmark ranges"],
        "owner_action": "Continue monitoring. Use as comparison baseline.",
        "color": "green",
    },
}

# ── PRICING BENCHMARKS ────────────────────────────────────────────────────────
# Opendoor offer vs market estimated value — healthy operating bands

PRICING_BANDS = {
    "entry_level": {"target_pct": -0.5, "warn_above": 2.0, "warn_below": -4.0},
    "mid_tier":    {"target_pct": -1.0, "warn_above": 3.0, "warn_below": -5.0},
    "premium":     {"target_pct": -1.5, "warn_above": 2.5, "warn_below": -6.0},
    "default":     {"target_pct": -1.0, "warn_above": 3.0, "warn_below": -5.0},
}

# ── FUNNEL BENCHMARKS ─────────────────────────────────────────────────────────
# Healthy conversion rates by stage — deviations trigger diagnostics

FUNNEL_BENCHMARKS = {
    "list_to_sale_ratio_healthy": 0.98,
    "list_to_sale_ratio_warn":    0.95,
    "list_to_sale_ratio_critical": 0.92,
    "homes_sold_mom_warn":        -0.10,   # -10% MoM = warning
    "homes_sold_mom_critical":    -0.20,   # -20% MoM = critical
    "dom_healthy":                35,
    "dom_warn":                   50,
    "dom_critical":               65,
}

# ── IMPACT MODEL ──────────────────────────────────────────────────────────────
# Used by estimate_business_impact() to translate signals into dollar terms

IMPACT_MODEL = {
    "avg_homes_per_market_per_month": 200,     # baseline acquisition volume
    "avg_acquisition_price": 380000,
    "avg_margin_pct": 0.055,                   # ~5.5% gross margin
    "holding_cost_per_day": 95,                # ~$95/day per home
    "acceptance_rate_elasticity": 1.8,         # 1% pricing change → 1.8% acceptance change
}


# ── TOOL 1: PRICING ACCURACY ──────────────────────────────────────────────────

def analyze_pricing_accuracy(market: str = None, segment: str = None) -> dict:
    """
    Analyze how Opendoor's offer prices align with market estimated values.

    Uses list_to_sale_ratio as a proxy for offer competitiveness:
      - ratio > 1.00: offers above market → seller-friendly but margin risk
      - ratio < 0.95: offers below market → conversion risk
      - ratio 0.96–0.99: healthy band

    Returns pricing deviation signals, acceptance proxy, elasticity estimate,
    and whether pricing is within acceptable band by market/segment.
    """
    df = load_market_data()

    if market:
        df = df[df["market"].str.lower() == market.lower()]
        if df.empty:
            return {"error": f"No data for market: {market}"}

    results = []

    for mkt in df["market"].unique():
        mdf = df[df["market"] == mkt].sort_values("date")

        latest = mdf.iloc[-1]
        prev   = mdf.iloc[-2]

        lsr_current = float(latest["list_to_sale_ratio"])
        lsr_prev    = float(prev["list_to_sale_ratio"])
        lsr_avg     = float(mdf["list_to_sale_ratio"].mean())

        # Derive offer deviation from market value using LSR
        # LSR > 1.0 means homes selling above list → tight market / competitive offers
        # LSR < 0.95 means homes selling below list → buyer leverage / offers too high
        offer_deviation_pct = round((lsr_current - 1.0) * 100, 2)
        deviation_wow = round((lsr_current - lsr_prev) * 100, 2)

        # Pricing band assessment (using default band since we don't have segment data in CSV)
        band = PRICING_BANDS.get(segment, PRICING_BANDS["default"])
        in_band = band["warn_below"] <= offer_deviation_pct <= band["warn_above"]

        # Elasticity: how much has acceptance proxy moved per unit of pricing change
        # Proxied by: homes_sold change vs LSR change
        sold_change = float(latest["homes_sold"]) - float(prev["homes_sold"])
        sold_pct_change = round(sold_change / float(prev["homes_sold"]) * 100, 1)

        if abs(deviation_wow) > 0.01:
            elasticity = round(abs(sold_pct_change / deviation_wow), 2)
        else:
            elasticity = None

        # Severity
        if abs(offer_deviation_pct) > 4.0 or lsr_current < FUNNEL_BENCHMARKS["list_to_sale_ratio_critical"]:
            severity = "critical"
        elif abs(offer_deviation_pct) > 2.5 or lsr_current < FUNNEL_BENCHMARKS["list_to_sale_ratio_warn"]:
            severity = "high"
        elif abs(offer_deviation_pct) > 1.5:
            severity = "medium"
        else:
            severity = "healthy"

        # Pricing direction signal
        # LSR < 0.95: homes sell well below list → buyers have leverage → offers too high relative to market
        # LSR > 1.02: homes sell above list → very competitive → offers may be undershooting
        # LSR 0.95-1.02: healthy band
        if lsr_current <= FUNNEL_BENCHMARKS["list_to_sale_ratio_warn"]:
            direction_signal = "PRICING_DRIFT — pricing outside observed acceptance behavior, conversion at risk"
        elif lsr_current > 1.02:
            direction_signal = "MARKET_ABOVE_LIST — very competitive, Opendoor offers may be undershooting"
        else:
            direction_signal = "IN_BAND — pricing aligned with market"

        results.append({
            "market": mkt,
            "segment": segment or "all",
            "list_to_sale_ratio": lsr_current,
            "list_to_sale_ratio_prev": lsr_prev,
            "list_to_sale_ratio_avg": round(lsr_avg, 3),
            "offer_deviation_pct": offer_deviation_pct,
            "deviation_wow_pts": deviation_wow,
            "pricing_band": band,
            "in_pricing_band": in_band,
            "direction_signal": direction_signal,
            "acceptance_proxy_change_pct": sold_pct_change,
            "pricing_elasticity": elasticity,
            "severity": severity,
            "median_price": int(latest["median_sale_price"]),
            "price_per_sqft": int(latest["price_per_sqft"]),
        })

    results.sort(key=lambda x: {"critical": 0, "high": 1, "medium": 2, "healthy": 3}[x["severity"]])

    return {
        "tool": "analyze_pricing_accuracy",
        "market_filter": market,
        "segment_filter": segment,
        "markets_analyzed": len(results),
        "markets_with_issues": sum(1 for r in results if r["severity"] in ("critical", "high")),
        "pricing_band_reference": PRICING_BANDS,
        "results": results,
    }


# ── TOOL 2: FUNNEL DIAGNOSTICS ────────────────────────────────────────────────

def analyze_funnel_drop(market: str = None) -> dict:
    """
    Diagnose conversion funnel health for a market.

    Funnel stages:
      Inventory listed → Homes sold (acceptance proxy)
      DOM trend → Velocity signal
      List-to-sale ratio → Pricing signal

    Identifies WHERE in the funnel conversion is dropping and likely WHY.
    Returns stage-by-stage breakdown with severity, WoW deltas, and root cause signal.
    """
    df = load_market_data()

    if market:
        df = df[df["market"].str.lower() == market.lower()]
        if df.empty:
            return {"error": f"No data for market: {market}"}

    funnel_results = []

    for mkt in df["market"].unique():
        mdf = df[df["market"] == mkt].sort_values("date")

        latest = mdf.iloc[-1]
        prev   = mdf.iloc[-2]
        avg    = mdf.mean(numeric_only=True)

        # Stage 1: Inventory → Listing velocity
        inv_current  = int(latest["inventory"])
        inv_prev     = int(prev["inventory"])
        inv_mom      = round((inv_current - inv_prev) / inv_prev * 100, 1)

        # Stage 2: Listing → Sale conversion (homes_sold / inventory)
        conversion_current = round(float(latest["homes_sold"]) / float(latest["inventory"]) * 100, 1)
        conversion_prev    = round(float(prev["homes_sold"]) / float(prev["inventory"]) * 100, 1)
        conversion_avg     = round(float(avg["homes_sold"]) / float(avg["inventory"]) * 100, 1)
        conversion_wow     = round(conversion_current - conversion_prev, 1)

        # Stage 3: Acceptance signal (list-to-sale ratio)
        lsr_current = float(latest["list_to_sale_ratio"])
        lsr_prev    = float(prev["list_to_sale_ratio"])
        lsr_wow     = round(lsr_current - lsr_prev, 3)

        # Stage 4: Time-on-market (velocity signal)
        dom_current = int(latest["days_on_market"])
        dom_prev    = int(prev["days_on_market"])
        dom_avg     = round(float(avg["days_on_market"]))
        dom_wow     = dom_current - dom_prev
        dom_vs_avg  = dom_current - dom_avg

        # Volume signal
        sold_current = int(latest["homes_sold"])
        sold_prev    = int(prev["homes_sold"])
        sold_mom     = round((sold_current - sold_prev) / sold_prev * 100, 1)

        # Identify bottleneck stage
        if lsr_current < FUNNEL_BENCHMARKS["list_to_sale_ratio_warn"] and lsr_wow < -0.01:
            bottleneck = "PRICING — offer-to-acceptance stage. Pricing drifting outside observed acceptance behavior."
            bottleneck_stage = "offer_acceptance"
        elif dom_wow > 5 and dom_vs_avg > 8:
            bottleneck = "VELOCITY — time-on-market expanding. Demand softening or pricing mismatch."
            bottleneck_stage = "market_absorption"
        elif inv_mom > 10 and sold_mom < -5:
            bottleneck = "INVENTORY BUILD — supply outpacing demand. Market turning to buyer's favor."
            bottleneck_stage = "supply_demand_imbalance"
        elif conversion_wow < -3:
            bottleneck = "CONVERSION — fewer listings converting to sales. Multi-factor pressure."
            bottleneck_stage = "conversion_rate"
        else:
            bottleneck = "NO CLEAR BOTTLENECK — funnel operating within normal range."
            bottleneck_stage = "healthy"

        # Overall severity
        issues = sum([
            lsr_current < FUNNEL_BENCHMARKS["list_to_sale_ratio_warn"],
            dom_wow > 5,
            sold_mom < FUNNEL_BENCHMARKS["homes_sold_mom_warn"] * 100,
            conversion_wow < -3,
            inv_mom > 12,
        ])
        severity = "critical" if issues >= 4 else "high" if issues >= 3 else "medium" if issues >= 2 else "low" if issues >= 1 else "healthy"

        funnel_results.append({
            "market": mkt,
            "severity": severity,
            "bottleneck": bottleneck,
            "bottleneck_stage": bottleneck_stage,
            "funnel_stages": {
                "inventory": {
                    "current": inv_current,
                    "mom_change_pct": inv_mom,
                    "signal": "building" if inv_mom > 5 else "stable" if inv_mom > -5 else "shrinking",
                },
                "conversion_rate": {
                    "current_pct": conversion_current,
                    "prev_pct": conversion_prev,
                    "avg_pct": conversion_avg,
                    "wow_pts": conversion_wow,
                    "signal": "deteriorating" if conversion_wow < -2 else "stable",
                },
                "acceptance_proxy": {
                    "list_to_sale_ratio": lsr_current,
                    "wow_change": lsr_wow,
                    "benchmark_healthy": FUNNEL_BENCHMARKS["list_to_sale_ratio_healthy"],
                    "signal": "below_benchmark" if lsr_current < FUNNEL_BENCHMARKS["list_to_sale_ratio_warn"] else "healthy",
                },
                "velocity": {
                    "days_on_market": dom_current,
                    "wow_change_days": dom_wow,
                    "vs_market_avg": dom_vs_avg,
                    "benchmark_warn": FUNNEL_BENCHMARKS["dom_warn"],
                    "signal": "slowing" if dom_current > FUNNEL_BENCHMARKS["dom_warn"] else "normal",
                },
                "volume": {
                    "homes_sold": sold_current,
                    "mom_change_pct": sold_mom,
                    "signal": "declining" if sold_mom < -10 else "stable",
                },
            },
        })

    funnel_results.sort(key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3, "healthy": 4}[x["severity"]])

    return {
        "tool": "analyze_funnel_drop",
        "market_filter": market,
        "markets_analyzed": len(funnel_results),
        "markets_with_funnel_issues": sum(1 for r in funnel_results if r["severity"] not in ("healthy", "low")),
        "results": funnel_results,
    }


# ── TOOL 3: PRICING ACTIONS ───────────────────────────────────────────────────

def generate_pricing_actions(market: str, segment: str = "all") -> dict:
    """
    Generate specific, actionable pricing recommendations for a market.

    Based on pricing deviation and funnel signals, recommends:
      - adjustment range (e.g. -3% to -5% on offer band)
      - which ZIP clusters / segments to target first
      - expected impact on acceptance rate
      - confidence level
      - owner (pricing team vs market-ops)

    This is the "decision packet" output — not insight, but action.
    """
    pricing = analyze_pricing_accuracy(market=market, segment=segment)
    funnel  = analyze_funnel_drop(market=market)

    if "error" in pricing:
        return pricing

    p = pricing["results"][0] if pricing["results"] else {}
    f = funnel["results"][0] if funnel["results"] else {}

    lsr     = p.get("list_to_sale_ratio", 0.97)
    dev_pct = p.get("offer_deviation_pct", 0.0)
    severity = p.get("severity", "healthy")
    bottleneck = f.get("bottleneck_stage", "healthy")

    # Determine adjustment direction and magnitude
    if lsr < FUNNEL_BENCHMARKS["list_to_sale_ratio_critical"]:
        adj_low, adj_high = -4.0, -6.0
        urgency = "IMMEDIATE — execute within 48 hours"
        confidence = "High"
    elif lsr < FUNNEL_BENCHMARKS["list_to_sale_ratio_warn"]:
        adj_low, adj_high = -2.5, -4.0
        urgency = "THIS WEEK — execute before next weekly review"
        confidence = "High"
    elif lsr < FUNNEL_BENCHMARKS["list_to_sale_ratio_healthy"] and dev_pct < -1.0:
        adj_low, adj_high = -1.0, -2.5
        urgency = "MONITOR — adjust if trend continues next week"
        confidence = "Medium-High"
    elif lsr > 1.01:
        adj_low, adj_high = 1.0, 2.5
        urgency = "OPPORTUNITY — offers may be undershooting, test upward band"
        confidence = "Medium"
    else:
        adj_low, adj_high = 0.0, 0.0
        urgency = "NO ACTION — pricing within healthy band"
        confidence = "High"

    # Elasticity-based impact estimate
    elasticity = p.get("pricing_elasticity") or IMPACT_MODEL["acceptance_rate_elasticity"]
    adj_midpoint = abs((adj_low + adj_high) / 2)
    expected_acceptance_recovery = round(adj_midpoint * elasticity, 1)

    # Build action list
    actions = []

    if adj_low != 0.0:
        if adj_low < 0:
            actions.append(
                f"Narrow offer band by {abs(adj_high):.0f}%–{abs(adj_low):.0f}% in {market} "
                f"{'(' + segment + ') ' if segment != 'all' else ''}starting with highest-DOM ZIP clusters."
            )
            actions.append(
                f"Re-run pricing model inputs for {market} {segment} segment — "
                f"current list-to-sale ratio ({lsr:.2f}) indicates pricing is drifting outside observed acceptance behavior."
            )
        else:
            actions.append(
                f"Test 1%–2% upward offer band adjustment in {market} — "
                f"LSR above 1.0 indicates market pricing above current offer levels."
            )

    if bottleneck == "market_absorption":
        actions.append(
            f"Prioritize disposition review for {market} homes >60 days DOM — "
            f"velocity signal indicates demand softening independent of pricing."
        )
    elif bottleneck == "supply_demand_imbalance":
        actions.append(
            f"Pause new acquisitions in {market} until inventory-to-sales ratio normalizes — "
            f"supply outpacing demand will compress margins further."
        )

    if not actions:
        actions.append(f"{market} pricing is within healthy band. Continue monitoring weekly.")

    # Segment prioritization
    segment_priority = []
    if segment == "all":
        segment_priority = [
            {"segment": "mid_tier", "priority": 1, "reason": "Highest volume, most elastic to pricing changes"},
            {"segment": "entry_level", "priority": 2, "reason": "Affordability sensitive — pricing deviations hit conversion hard"},
            {"segment": "premium", "priority": 3, "reason": "Lower volume, longer DOM tolerance — monitor but less urgent"},
        ]

    # Expected outcome — forward-looking, measurable
    if adj_low < 0:
        expected_outcome = {
            "acceptance_rate_improvement_pct": f"+{expected_acceptance_recovery}%",
            "homes_recovered_per_month": round(
                (abs(adj_low + adj_high) / 2) * IMPACT_MODEL["acceptance_rate_elasticity"]
                * IMPACT_MODEL["avg_homes_per_market_per_month"] / 100
            ),
            "margin_recovered_per_month": round(
                (abs(adj_low + adj_high) / 2) * IMPACT_MODEL["acceptance_rate_elasticity"]
                * IMPACT_MODEL["avg_homes_per_market_per_month"] / 100
                * IMPACT_MODEL["avg_acquisition_price"]
                * IMPACT_MODEL["avg_margin_pct"]
            ),
            "timeframe": "Expected improvement visible within 2–3 weeks of adjustment",
            "measurement": "Track LSR and weekly accepted_offer_count vs prior 4-week average",
        }
    elif adj_low > 0:
        expected_outcome = {
            "volume_uplift_pct": f"+{expected_acceptance_recovery}%",
            "additional_acquisitions_per_month": round(
                adj_midpoint * IMPACT_MODEL["acceptance_rate_elasticity"]
                * IMPACT_MODEL["avg_homes_per_market_per_month"] / 100
            ),
            "timeframe": "Test upward band for 2 weeks before full rollout",
            "measurement": "Track acceptance rate — confirm no drop before widening band further",
        }
    else:
        expected_outcome = {
            "note": "No adjustment warranted. Pricing within healthy band.",
            "measurement": "Continue weekly LSR monitoring",
        }

    # Severity metadata
    sev_meta = SEVERITY_FRAMEWORK.get(severity, SEVERITY_FRAMEWORK["medium"])

    return {
        "tool": "generate_pricing_actions",
        "market": market,
        "segment": segment,
        "pricing_signal": {
            "list_to_sale_ratio": lsr,
            "offer_deviation_pct": dev_pct,
            "severity": severity,
            "severity_sla": sev_meta["sla"],
            "owner_action_required": sev_meta["owner_action"],
            "funnel_bottleneck": bottleneck,
        },
        "recommendation": {
            "adjustment_range_pct": {"low": adj_low, "high": adj_high},
            "urgency": urgency,
            "expected_acceptance_recovery_pct": expected_acceptance_recovery,
            "confidence": confidence,
            "owner": "pricing" if bottleneck in ("offer_acceptance", "healthy") else "market-ops",
            "actions": actions,
            "segment_priority": segment_priority,
        },
        "expected_outcome": expected_outcome,
    }


# ── TOOL 4: BUSINESS IMPACT ESTIMATOR ────────────────────────────────────────

def estimate_business_impact(market: str, issue_type: str = "pricing_misalignment") -> dict:
    """
    Translate a detected issue into unit economics terms.

    Answers: "What does this actually cost us?"
    Outputs in homes/month, margin dollars, and holding cost dollars.

    issue_type options:
      "pricing_misalignment" — impact of offer-acceptance drop on acquisition volume + margin
      "inventory_aging"      — impact of rising DOM on holding costs
      "funnel_deterioration" — impact of conversion drop on monthly volume and revenue
    """
    df = load_market_data()
    mdf = df[df["market"].str.lower() == market.lower()].sort_values("date")

    if mdf.empty:
        return {"error": f"No data for market: {market}"}

    latest = mdf.iloc[-1]
    prev   = mdf.iloc[-2]

    median_price = int(latest["median_sale_price"])
    homes_sold   = int(latest["homes_sold"])
    dom_current  = int(latest["days_on_market"])
    dom_prev     = int(prev["days_on_market"])
    lsr_current  = float(latest["list_to_sale_ratio"])
    lsr_prev     = float(prev["list_to_sale_ratio"])

    avg_margin    = IMPACT_MODEL["avg_margin_pct"]
    hold_per_day  = IMPACT_MODEL["holding_cost_per_day"]
    elasticity    = IMPACT_MODEL["acceptance_rate_elasticity"]

    if issue_type == "pricing_misalignment":
        # How much did acceptance proxy drop?
        lsr_drop_pct = round((lsr_current - lsr_prev) * 100, 2)
        acceptance_drop_pct = round(abs(lsr_drop_pct) * elasticity, 1)

        # Homes lost per month
        homes_lost_monthly = round(homes_sold * acceptance_drop_pct / 100)
        margin_at_risk = round(homes_lost_monthly * median_price * avg_margin)
        revenue_at_risk = round(homes_lost_monthly * median_price)

        # Recovery potential if pricing fixed
        recovery_homes = homes_lost_monthly
        recovery_margin = margin_at_risk

        impact = {
            "issue_type": "Pricing Misalignment",
            "market": market,
            "signal": f"LSR moved {lsr_drop_pct:+.2f}pts → estimated {acceptance_drop_pct}% acceptance drop",
            "homes_lost_per_month": homes_lost_monthly,
            "revenue_at_risk_monthly": revenue_at_risk,
            "margin_at_risk_monthly": margin_at_risk,
            "recovery_if_fixed": {
                "homes_recovered": recovery_homes,
                "margin_recovered": recovery_margin,
            },
            "annualized_margin_at_risk": margin_at_risk * 12,
        }

    elif issue_type == "inventory_aging":
        dom_increase = dom_current - dom_prev
        extra_hold_cost_per_home = round(dom_increase * hold_per_day)
        total_inventory = int(latest["inventory"])
        total_extra_hold_cost = round(extra_hold_cost_per_home * total_inventory)
        pct_aging = round(max(0, dom_current - 45) / 45 * 100, 1)  # % above 45-day baseline

        impact = {
            "issue_type": "Inventory Aging",
            "market": market,
            "signal": f"DOM increased {dom_increase:+d} days → extra holding cost accumulating",
            "current_dom": dom_current,
            "dom_increase_wow": dom_increase,
            "extra_hold_cost_per_home": extra_hold_cost_per_home,
            "total_inventory": total_inventory,
            "total_extra_hold_cost_monthly": total_extra_hold_cost,
            "pct_above_healthy_baseline": pct_aging,
            "annualized_hold_cost_at_risk": total_extra_hold_cost * 12,
        }

    elif issue_type == "funnel_deterioration":
        sold_change = homes_sold - int(prev["homes_sold"])
        sold_change_pct = round(sold_change / int(prev["homes_sold"]) * 100, 1)
        margin_impact = round(abs(sold_change) * median_price * avg_margin)
        revenue_impact = round(abs(sold_change) * median_price)

        impact = {
            "issue_type": "Funnel Deterioration",
            "market": market,
            "signal": f"Homes sold {sold_change:+d} MoM ({sold_change_pct}%) — funnel converting fewer leads",
            "volume_change": sold_change,
            "volume_change_pct": sold_change_pct,
            "revenue_impact_monthly": revenue_impact,
            "margin_impact_monthly": margin_impact,
            "annualized_margin_impact": margin_impact * 12,
        }

    else:
        return {"error": f"Unknown issue_type: {issue_type}. Use: pricing_misalignment, inventory_aging, funnel_deterioration"}

    return {"tool": "estimate_business_impact", **impact}
