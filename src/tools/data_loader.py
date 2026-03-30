import pandas as pd
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent / "data" / "housing_market.csv"


def load_market_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, parse_dates=["date"])
    return df


def get_market_summary(market: str = None) -> dict:
    df = load_market_data()
    if market:
        df = df[df["market"].str.lower() == market.lower()]
        if df.empty:
            return {"error": f"No data found for market: {market}"}

    latest = df.sort_values("date").groupby("market").last().reset_index()

    summary = []
    for _, row in latest.iterrows():
        summary.append({
            "market": row["market"],
            "latest_date": str(row["date"].date()),
            "median_sale_price": int(row["median_sale_price"]),
            "days_on_market": int(row["days_on_market"]),
            "homes_sold": int(row["homes_sold"]),
            "inventory": int(row["inventory"]),
            "list_to_sale_ratio": float(row["list_to_sale_ratio"]),
            "price_per_sqft": int(row["price_per_sqft"]),
        })
    return {"markets": summary}


def get_market_trend(market: str, metric: str = "median_sale_price") -> dict:
    df = load_market_data()
    df = df[df["market"].str.lower() == market.lower()].sort_values("date")

    if df.empty:
        return {"error": f"No data found for market: {market}"}

    values = df[metric].tolist()
    dates = df["date"].dt.strftime("%Y-%m").tolist()
    change_pct = round((values[-1] - values[0]) / values[0] * 100, 1)

    return {
        "market": market,
        "metric": metric,
        "trend": list(zip(dates, values)),
        "start_value": values[0],
        "end_value": values[-1],
        "change_pct": change_pct,
        "direction": "up" if change_pct > 0 else "down",
    }


def detect_anomalies(market: str = None) -> dict:
    df = load_market_data()
    if market:
        df = df[df["market"].str.lower() == market.lower()]

    anomalies = []
    for mkt in df["market"].unique():
        mdf = df[df["market"] == mkt].sort_values("date")
        for metric in ["median_sale_price", "days_on_market", "homes_sold"]:
            mean = mdf[metric].mean()
            std = mdf[metric].std()
            latest_val = mdf[metric].iloc[-1]
            z_score = (latest_val - mean) / std if std > 0 else 0
            if abs(z_score) > 1.5:
                anomalies.append({
                    "market": mkt,
                    "metric": metric,
                    "latest_value": float(round(latest_val, 2)),
                    "average": float(round(mean, 2)),
                    "deviation": float(round(z_score, 2)),
                    "signal": "above average" if z_score > 0 else "below average",
                })

    return {"anomalies": anomalies, "count": len(anomalies)}
