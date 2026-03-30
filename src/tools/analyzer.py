import pandas as pd
from src.tools.data_loader import load_market_data, detect_anomalies, get_market_trend


def score_market_risk(market: str) -> dict:
    """Score a market 1-10 for acquisition risk. Higher = riskier."""
    df = load_market_data()
    mdf = df[df["market"] == market].sort_values("date")

    latest = mdf.iloc[-1]
    prev = mdf.iloc[-2]

    score = 0
    reasons = []

    # Days on market rising
    dom_change = latest["days_on_market"] - prev["days_on_market"]
    if dom_change > 5:
        score += 2
        reasons.append(f"DOM rising fast (+{dom_change} days month-over-month)")
    elif dom_change > 0:
        score += 1
        reasons.append(f"DOM creeping up (+{dom_change} days)")

    # Homes sold declining
    sold_change_pct = (latest["homes_sold"] - prev["homes_sold"]) / prev["homes_sold"] * 100
    if sold_change_pct < -10:
        score += 2
        reasons.append(f"Sales volume dropping fast ({sold_change_pct:.1f}% MoM)")
    elif sold_change_pct < 0:
        score += 1
        reasons.append(f"Sales volume declining ({sold_change_pct:.1f}% MoM)")

    # List-to-sale ratio below 1
    lsr = latest["list_to_sale_ratio"]
    if lsr < 0.95:
        score += 2
        reasons.append(f"List-to-sale ratio at {lsr} — buyers have strong leverage")
    elif lsr < 0.98:
        score += 1
        reasons.append(f"List-to-sale ratio softening ({lsr})")

    # Inventory vs sales (months of supply)
    months_supply = latest["inventory"] / latest["homes_sold"]
    if months_supply > 4.5:
        score += 2
        reasons.append(f"High months of supply ({months_supply:.1f} months — buyer's market)")
    elif months_supply > 3:
        score += 1
        reasons.append(f"Inventory building ({months_supply:.1f} months of supply)")

    # Price declining
    price_change_pct = (latest["median_sale_price"] - prev["median_sale_price"]) / prev["median_sale_price"] * 100
    if price_change_pct < -1:
        score += 2
        reasons.append(f"Prices declining ({price_change_pct:.1f}% MoM)")
    elif price_change_pct < 0:
        score += 1
        reasons.append(f"Prices softening ({price_change_pct:.1f}% MoM)")

    score = min(score, 10)
    risk_level = "HIGH" if score >= 7 else "MEDIUM" if score >= 4 else "LOW"

    return {
        "market": market,
        "risk_score": score,
        "risk_level": risk_level,
        "reasons": reasons,
        "months_supply": round(months_supply, 1),
        "dom": int(latest["days_on_market"]),
        "median_price": int(latest["median_sale_price"]),
        "list_to_sale": float(lsr),
    }


def rank_all_markets() -> dict:
    df = load_market_data()
    markets = df["market"].unique().tolist()
    scores = [score_market_risk(m) for m in markets]
    scores.sort(key=lambda x: x["risk_score"], reverse=True)
    return {"rankings": scores}
