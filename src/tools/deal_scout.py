import random
from src.tools.data_loader import load_market_data

RENOVATION_TIERS = {
    "cosmetic": {
        "cost_per_sqft_range": (12, 22),
        "arv_multiplier": 1.12,
        "description": "Paint, flooring, fixtures, landscaping",
    },
    "moderate": {
        "cost_per_sqft_range": (28, 45),
        "arv_multiplier": 1.25,
        "description": "Kitchen, bathrooms, HVAC, windows",
    },
    "full_gut": {
        "cost_per_sqft_range": (55, 90),
        "arv_multiplier": 1.42,
        "description": "Full structural remodel, new systems",
    },
}

MARKET_STREETS = {
    "Phoenix":   ["Camelback Rd", "McDowell Rd", "Indian School Rd", "Glendale Ave", "Bethany Home Rd", "Thomas Rd"],
    "Atlanta":   ["Peachtree St", "Ponce de Leon Ave", "Piedmont Ave", "Moreland Ave", "Howell Mill Rd", "Virginia Ave"],
    "Dallas":    ["Mockingbird Ln", "Lovers Ln", "Greenville Ave", "Henderson Ave", "Ross Ave", "Skillman St"],
    "Charlotte": ["Providence Rd", "Monroe Rd", "Independence Blvd", "Central Ave", "Woodlawn Rd", "Sharon Rd"],
}


def _generate_deals(seed: int = 42) -> list:
    rng = random.Random(seed)
    df = load_market_data()
    latest = df.sort_values("date").groupby("market").last().reset_index()

    deals = []
    deal_id = 1

    for _, row in latest.iterrows():
        market = row["market"]
        median_price = row["median_sale_price"]
        dom = int(row["days_on_market"])
        streets = MARKET_STREETS.get(market, ["Main St"])

        for _ in range(25):
            sqft = rng.randint(1100, 3200)
            beds = rng.choices([3, 4, 5], weights=[55, 35, 10])[0]
            baths = rng.choice([2, 2, 2.5, 3])
            condition = rng.choices(
                ["cosmetic", "moderate", "full_gut"],
                weights=[50, 35, 15],
            )[0]

            # Price/sqft for this property (slight variance around market avg)
            ppsf = row["price_per_sqft"] * rng.uniform(0.88, 1.12)
            full_market_value = round(ppsf * sqft / 1000) * 1000

            # Buyer discount: distressed properties sell below market value
            condition_discount = {"cosmetic": 0.94, "moderate": 0.84, "full_gut": 0.72}
            asking_price = round(full_market_value * condition_discount[condition] / 1000) * 1000

            # Higher DOM = more negotiating room off asking
            dom_discount = min(0.06, max(0, (dom - 30) * 0.0015))
            acquisition_price = round(asking_price * (1 - dom_discount))

            tier = RENOVATION_TIERS[condition]
            reno_rate = rng.uniform(*tier["cost_per_sqft_range"])
            reno_cost = round(sqft * reno_rate / 1000) * 1000

            # ARV = post-reno market value (uplift applied to full market value, not buy price)
            arv = round(full_market_value * tier["arv_multiplier"] / 1000) * 1000
            holding_cost = round(acquisition_price * 0.022)   # ~90-day carry
            selling_cost = round(arv * 0.06)                  # agent + closing
            total_cost = acquisition_price + reno_cost + holding_cost + selling_cost
            net_profit = arv - total_cost
            total_capital = acquisition_price + reno_cost
            roi = round(net_profit / total_capital * 100, 1) if total_capital > 0 else 0

            address = f"{rng.randint(100, 9999)} {rng.choice(streets)}"
            prop_dom = max(1, dom + rng.randint(-15, 25))

            deals.append({
                "deal_id": f"DEAL-{deal_id:03d}",
                "market": market,
                "address": address,
                "beds": beds,
                "baths": baths,
                "sqft": sqft,
                "condition": condition,
                "reno_scope": tier["description"],
                "asking_price": asking_price,
                "acquisition_price": acquisition_price,
                "reno_cost": reno_cost,
                "holding_cost": holding_cost,
                "selling_cost": selling_cost,
                "arv": arv,
                "net_profit": net_profit,
                "total_capital_required": total_capital,
                "roi_pct": roi,
                "days_on_market": prop_dom,
            })
            deal_id += 1

    return deals


def get_top_deals(
    market: str = None,
    max_capital: int = None,
    min_roi: float = None,
    limit: int = 100,
) -> dict:
    """
    Return top deals ranked by ROI.
    Filters: market, max_capital (total acquisition + reno budget), min_roi (%).
    """
    deals = _generate_deals()

    if market:
        deals = [d for d in deals if d["market"].lower() == market.lower()]
    if max_capital:
        deals = [d for d in deals if d["total_capital_required"] <= max_capital]
    if min_roi is not None:
        deals = [d for d in deals if d["roi_pct"] >= min_roi]

    deals = [d for d in deals if d["net_profit"] > 0]
    deals.sort(key=lambda x: x["roi_pct"], reverse=True)
    deals = deals[:limit]

    avg_roi = round(sum(d["roi_pct"] for d in deals) / len(deals), 1) if deals else 0
    avg_profit = round(sum(d["net_profit"] for d in deals) / len(deals)) if deals else 0

    return {
        "total_deals_returned": len(deals),
        "filters": {"market": market, "max_capital": max_capital, "min_roi": min_roi},
        "summary": {"avg_roi_pct": avg_roi, "avg_net_profit": avg_profit},
        "deals": deals,
    }


def estimate_renovation(condition: str, sqft: int, capital_budget: int = None) -> dict:
    """
    Estimate renovation cost range for a property.
    Optionally check whether it fits within a capital budget.
    """
    if condition not in RENOVATION_TIERS:
        return {"error": f"Unknown condition '{condition}'. Use: cosmetic, moderate, full_gut"}

    tier = RENOVATION_TIERS[condition]
    low  = round(sqft * tier["cost_per_sqft_range"][0] / 1000) * 1000
    high = round(sqft * tier["cost_per_sqft_range"][1] / 1000) * 1000
    mid  = round((low + high) / 2 / 1000) * 1000

    result = {
        "condition": condition,
        "sqft": sqft,
        "scope": tier["description"],
        "reno_cost_low": low,
        "reno_cost_mid": mid,
        "reno_cost_high": high,
        "arv_uplift_multiplier": tier["arv_multiplier"],
        "arv_uplift_note": f"+{round((tier['arv_multiplier'] - 1) * 100)}% expected value increase post-reno",
    }

    if capital_budget is not None:
        result["fits_budget"] = mid <= capital_budget
        result["budget_remaining_after_reno"] = capital_budget - mid

    return result
