# Opendoor Agentic Analytics Assistant
### From Reactive Dashboards to Proactive Intelligence

---

## Slide 1 — The Problem

**Most analytics teams are stuck in reactive mode.**

```
Business Leader:  "What happened in Phoenix last month?"
                              ↓
Analyst:          Opens dashboard → pulls data → writes report
                              ↓
                         2 hours later
                              ↓
Business Leader:  "Thanks. What should we DO about it?"
                              ↓
Analyst:          Starts over...
```

**The result:**
- Dashboards go stale the moment they're built
- Leaders make decisions without real-time signal
- Analysts spend 80% of time answering questions, 20% driving decisions

---

## Slide 2 — The Shift We're Making

```
❌ BEFORE: Reactive Analytics
   Leader asks → Analyst queries → Data returned → Human interprets

✅ AFTER: Proactive Intelligence
   Agent monitors → Detects signal → Surfaces insight → Recommends action
                    (no one asked)
```

> **"Don't wait to be asked. Know what matters before they do."**

---

## Slide 3 — What We Built

Two agents. One pipeline. Zero manual steps.

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│   AGENT 1: Analytics Agent      AGENT 2: Monitor    │
│   ─────────────────────────     ─────────────────   │
│   You ask a question        →   Runs automatically  │
│   Agent answers in 10 sec   →   No question needed  │
│   Natural language input    →   Saves daily report  │
│                                                     │
│              Both powered by Claude                 │
└─────────────────────────────────────────────────────┘
```

---

## Slide 4 — The Agentic Loop (How It Works)

```
                    ┌─────────────────────┐
                    │   Question / Timer  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Claude thinks:    │
                    │ "What data do I     │
                    │  need to answer?"   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Calls tool(s)      │◄──────┐
                    │  autonomously       │       │
                    └──────────┬──────────┘       │
                               │                  │
                               ▼                  │
                    ┌─────────────────────┐       │
                    │  Gets real data     │       │
                    │  back as JSON       │       │
                    └──────────┬──────────┘       │
                               │                  │
                               ▼                  │
                    ┌─────────────────────┐       │
                    │  "Do I need more    │  YES  │
                    │   data?"            │───────┘
                    └──────────┬──────────┘
                               │ NO
                               ▼
                    ┌─────────────────────┐
                    │  Synthesizes into:  │
                    │  • Insight          │
                    │  • Evidence         │
                    │  • Recommended      │
                    │    Action           │
                    └─────────────────────┘
```

**Key point:** Claude decides what to call, when to call it, and when it has enough. That's the agent.

---

## Slide 5 — The 4 Tools Available to the Agent

```
┌──────────────────────┬───────────────────────────────────────────┐
│ Tool                 │ What it does                              │
├──────────────────────┼───────────────────────────────────────────┤
│ get_market_summary   │ Latest snapshot: price, DOM, inventory,   │
│                      │ homes sold, list-to-sale ratio            │
├──────────────────────┼───────────────────────────────────────────┤
│ get_market_trend     │ 12-month history for any metric in any    │
│                      │ market — shows direction and momentum     │
├──────────────────────┼───────────────────────────────────────────┤
│ detect_anomalies     │ Statistical outlier detection (z-score)   │
│                      │ — flags what's unusual vs. history        │
├──────────────────────┼───────────────────────────────────────────┤
│ rank_all_markets     │ Scores every market 1-10 for acquisition  │
│                      │ risk across 5 weighted signals            │
└──────────────────────┴───────────────────────────────────────────┘
```

---

## Slide 6 — The Risk Scoring Engine

Every market gets a score (1-10) based on 5 signals:

```
Signal                    Weight    Trigger
─────────────────────     ──────    ──────────────────────────────
Days on market rising      2 pts   > 5 day month-over-month rise
Sales volume declining     2 pts   > 10% month-over-month drop
List-to-sale ratio soft    2 pts   Below 0.95
Months of supply high      2 pts   Above 4.5 months
Price declining            2 pts   Below -1% month-over-month

Score 7-10 → HIGH RISK   → Pause or tighten acquisitions
Score 4-6  → MEDIUM RISK → Proceed with caution
Score 1-3  → LOW RISK    → Favorable conditions
```

**March 29 results:**
```
Charlotte  9/10  ████████████████████ HIGH
Atlanta    8/10  ████████████████     HIGH
Dallas     7/10  ██████████████       HIGH
Phoenix    7/10  ██████████████       HIGH
```

---

## Slide 7 — Agent 1: Interactive Q&A Demo

**Question:** *"Where should we reduce acquisitions?"*

```
Agent calls: get_market_summary()       ← what does each market look like?
Agent calls: detect_anomalies()         ← what's statistically unusual?
Agent calls: get_market_trend(Phoenix)  ← confirm DOM trend
Agent calls: get_market_trend(Atlanta)  ← confirm inventory trend

Agent answers:

  Atlanta  → Cut 25-30%   (fastest DOM rise, deepest sales decline)
  Phoenix  → Cut 15-20%   (highest absolute inventory, DOM at 50 days)
  Dallas   → Hold steady  (softening but not broken)
  Charlotte→ Monitor       (similar signals, slightly less acute)
```

**6 tool calls. 10 seconds. Decision made.**

---

## Slide 8 — Agent 2: Proactive Monitor Demo

**No question asked. Runs automatically.**

```
7:00 AM — monitor.py triggers
           ↓
  [scanning: get_market_summary]
  [scanning: rank_all_markets]
  [scanning: detect_anomalies]
           ↓
  Generates briefing → saves to briefings/2026-03-29.md

EXECUTIVE SUMMARY:
• All 4 markets rated HIGH risk (scores 7-9)
• Sales volume down 35-43% — structural demand destruction
• Charlotte (9/10) is most urgent — pause acquisitions immediately

RECOMMENDED ACTIONS:
1. Charlotte — PAUSE all new acquisitions
2. Atlanta   — Stress-test portfolio at -10% price scenario
3. Dallas    — Opportunistic only, min 6% discount to comps
4. All       — Renegotiate any deals currently under contract

ESCALATION TRIGGER: Any market crossing 6.0 months of supply
```

---

## Slide 9 — Full System Architecture

```
   User / Scheduler
         │
         ▼
┌────────────────────────────────────────┐
│            Agent Layer                 │
│                                        │
│  analytics-agent    monitor-agent      │
│  (you ask)          (runs itself)      │
│       │                  │             │
└───────┼──────────────────┼─────────────┘
        │                  │
        ▼                  ▼
┌────────────────────────────────────────┐
│             Tool Layer                 │
│                                        │
│  get_market_summary  get_market_trend  │
│  detect_anomalies    rank_all_markets  │
└──────────────┬─────────────────────────┘
               │
               ▼
┌────────────────────────────────────────┐
│             Data Layer                 │
│  housing_market.csv                    │
│  → Snowflake / BigQuery in production  │
└──────────────┬─────────────────────────┘
               │
               ▼
┌────────────────────────────────────────┐
│            Output Layer                │
│  Terminal chat  │  Daily .md briefing  │
│  → Web UI       │  → Slack / Email     │
└────────────────────────────────────────┘
```

---

## Slide 10 — What Makes This Different

```
┌─────────────────────┬────────────────────────────────────────────┐
│ Regular Analytics   │ This Agent                                 │
├─────────────────────┼────────────────────────────────────────────┤
│ You ask             │ Monitors without being asked               │
│ Returns raw data    │ Returns insight + evidence + action        │
│ Human interprets    │ Agent interprets                           │
│ 2 hrs analyst time  │ 10 seconds                                 │
│ Dashboard goes stale│ Briefing runs fresh every day              │
│ 1 question = 1 query│ 1 question = multiple tool calls           │
│ Guesses at meaning  │ Reads real data before answering           │
└─────────────────────┴────────────────────────────────────────────┘
```

---

## Slide 11 — Production Roadmap

```
Phase 1 (Built today)         Phase 2                  Phase 3
──────────────────────        ─────────────────────    ──────────────────────
CSV dataset              →    Snowflake / BigQuery →   Real-time MLS feed
Manual run               →    Scheduled daily cron →   Event-triggered alerts
4 markets                →    All US markets       →   Zip-code granularity
Terminal output          →    Web UI (Streamlit)   →   Slack / email delivery
Static risk scores       →    ML-based forecasting →   Automated deal pricing
```

---

## Slide 12 — Tech Stack

```
Layer          Technology             Why
─────────────  ─────────────────────  ────────────────────────────────
AI Model       Claude claude-opus-4-6         Most capable reasoning model
Agent SDK      Anthropic Python SDK   Native tool use, no wrappers
Data           pandas + CSV           Clean, fast, portable
Config         python-dotenv          Secure secret handling
Language       Python 3.14            Industry standard for data/AI
Workspace      Claude Code            Production-grade agent setup
```

---

## Slide 13 — This Is What Opendoor Means by "Default to AI"

> *"If AI can handle it, AI should handle it."*

```
Before: Analytics team fields ad-hoc requests all day
After:  Agent monitors 24/7, escalates only what matters

Before: VP opens 5 dashboards to start the day
After:  VP reads one briefing with ranked priorities and actions

Before: "Let me pull that data and get back to you"
After:  Answer in the meeting, decision made on the spot

Before: Analyst = question answerer
After:  Analyst = AI systems builder
```

---

*Built by [Your Name] as a demonstration of agentic analytics engineering.*
*GitHub: github.com/YOUR_USERNAME/opendoor-agent*
