---
name: risk-analyzer
description: Score any real estate market 1-10 for acquisition risk using 5 weighted signals and rank all markets by priority.
---

# Skill: Risk Analyzer

## Purpose
Score any real estate market on a 1-10 acquisition risk scale using
5 weighted signals: DOM trend, sales velocity, list-to-sale ratio,
months of supply, and price momentum.

## When to Use
- Before approving acquisitions in a market
- When comparing markets for capital allocation
- During portfolio review meetings

## Scoring Logic
| Signal | Max Points | Trigger |
|--------|-----------|---------|
| Days on market rising | 2 | >5 day MoM increase |
| Sales volume declining | 2 | >10% MoM drop |
| List-to-sale ratio soft | 2 | <0.95 |
| Months of supply high | 2 | >4.5 months |
| Price declining | 2 | <-1% MoM |

**Score interpretation:**
- 7-10: HIGH risk — tighten or pause acquisitions
- 4-6: MEDIUM risk — proceed with caution
- 1-3: LOW risk — favorable conditions

## Run
```python
from src.tools.analyzer import score_market_risk, rank_all_markets
print(score_market_risk("Phoenix"))
print(rank_all_markets())
```
