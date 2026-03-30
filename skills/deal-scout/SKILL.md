---
name: deal-scout
description: Rank the top 100 acquisition deals by ROI with full P&L breakdown — acquisition cost, renovation estimate, ARV, net profit, and capital required.
---

# Skill: Deal Scout

## Purpose
Surface the highest-ROI acquisition opportunities across all markets with a
complete deal-level P&L: what it costs to buy, what it costs to fix, what it
sells for after repair, and what the net profit is — filtered by capital budget.

## When to Use
- Capital allocation meetings: "Where should we deploy the next $50M?"
- Weekly deal pipeline reviews
- Acquisition team briefings: "Show me the top 20 deals under $400k all-in"
- Renovation budget planning: "What can we do with $30k in reno budget?"

## How It Works
1. Calls `get_top_deals()` — generates 100 deals across all markets, ranked by ROI
2. Optionally filters by market, max capital, or minimum ROI threshold
3. Calls `estimate_renovation()` for deeper P&L on specific properties
4. Claude synthesizes into ranked deal list with action recommendations

## Renovation Tiers

| Tier | Scope | Cost/sqft | ARV Uplift |
|------|-------|-----------|-----------|
| cosmetic | Paint, flooring, fixtures, landscaping | $12–22 | +12% |
| moderate | Kitchen, baths, HVAC, windows | $28–45 | +25% |
| full_gut | Full structural remodel, new systems | $55–90 | +42% |

## P&L Formula Per Deal
```
Net Profit = ARV − Acquisition Price − Reno Cost − Holding Cost − Selling Cost
ROI %      = Net Profit / (Acquisition Price + Reno Cost) × 100
Total Capital Required = Acquisition Price + Reno Cost
```

## Output Format
- Deal ID, Market, Address, Beds/Baths/Sqft
- Condition tier + renovation scope
- Asking → Acquisition price (negotiation discount applied)
- Reno cost estimate
- ARV (After Repair Value)
- Net profit + ROI %
- Total capital required
- Recommended action

## Example Queries
```
"Show me the top 20 deals in Phoenix under $350k total capital"
"What's the ROI on a 1,800 sqft moderate reno in Atlanta?"
"Rank all full gut deals with ROI above 12%"
"Best deals for a $2M deployment across all markets"
```

## Run
```python
from src.tools.deal_scout import get_top_deals, estimate_renovation

# Top 10 deals under $400k all-in capital
print(get_top_deals(max_capital=400000, limit=10))

# Reno estimate for a 1,800 sqft moderate job
print(estimate_renovation("moderate", 1800, capital_budget=55000))
```
