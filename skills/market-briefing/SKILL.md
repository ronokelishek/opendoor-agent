---
name: market-briefing
description: Generate a proactive daily real estate market intelligence briefing with risk rankings and recommended actions.
---

# Skill: Market Briefing

## Purpose
Generate a proactive daily intelligence briefing for all real estate markets,
written in the analytical voice of top housing analysts (Ivy Zelman, Ken Zener,
Jay Parsons). No question needed — the agent decides what matters and surfaces it.

## When to Use
- Morning briefings for leadership
- Before acquisition meetings
- When monitoring market conditions at scale

## How It Works
1. Calls `rank_all_markets()` to score all markets 1-10
2. Calls `detect_anomalies()` to find statistical outliers
3. Calls `get_market_summary()` for latest metrics
4. Synthesizes into a structured briefing with ranked recommendations

## Output Format
- Executive Summary (3 bullets)
- Risk Rankings Table
- Top Signals to Act On
- Recommended Actions This Week
- Leading Indicators to Watch

## Run
```bash
py -m src.monitor
```

## Example Output
See briefings/briefing_2026-03-29.md
