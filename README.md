# Opendoor Agentic Analytics System

> **"Most analytics teams answer questions. This system anticipates them — and tells you what it's going to cost if you don't act."**

Built as a portfolio demonstration for Opendoor's **Senior Agentic Analytics Engineer** role. This is a full analytics-to-action pipeline powered by Claude's native tool use — no LangChain, no wrappers, just the Anthropic SDK and clean Python.

---

## Live Demo

**[→ View the full portfolio](https://ronokelishek.github.io/opendoor-agent/portfolio.html)**

| Page | Live Link | What it shows |
|------|-----------|--------------|
| Portfolio Overview | [portfolio.html](https://ronokelishek.github.io/opendoor-agent/portfolio.html) | Full system walkthrough — Capital-Light strategy, deal scout, market risk |
| Decision Engine | [decision-engine.html](https://ronokelishek.github.io/opendoor-agent/decision-engine.html) | Pricing & Conversion alerts — Decision Packets, severity framework, feedback loop |
| Production Architecture | [production-architecture.html](https://ronokelishek.github.io/opendoor-agent/production-architecture.html) | AWS diagram — all upstream systems, Snowflake tables, real-time data flow |

---

## What This System Does

Two agents, running on different triggers:

```
analytics-agent    →  on-demand Q&A
                       "Which markets should I pause acquisitions in?"

monitor-agent      →  proactive daily scan — no question needed
                       Runs every morning, finds what matters before anyone asks
```

Every response follows the same output contract:

```
Issue     →  what is happening (evidence-grounded, specific)
Impact    →  what it's costing (homes/month, margin dollars, annualized)
Action    →  exactly what to do (owner assigned, urgency stated, 2–3 steps)
Outcome   →  what we expect to happen (measurable, time-bound)
```

---

## System Architecture

```
Upstream Sources (MLS, Offer DB, AVM, CRM, Reno Tracker)
        │
        ▼
AWS Ingestion (Kinesis · S3 · Glue / dbt)
        │
        ▼
Snowflake (raw.offer_events · mart.market_metrics · mart.deal_pl · mart.feedback_log)
        │
        ▼
Tool Layer  ──────────────────────────────────────────────────────────────
  data_loader.py      get_market_summary() · get_market_trend() · detect_anomalies()
  analyzer.py         score_market_risk() · rank_all_markets()
  deal_scout.py       get_top_deals() · estimate_renovation()
  capital_light.py    detect_inventory_surges() · get_contribution_margin_forecast() · rank_top_100_deals()
  pricing_engine.py   analyze_pricing_accuracy() · analyze_funnel_drop() · generate_pricing_actions() · estimate_business_impact()
  feedback_tracker.py log_recommendation() · record_outcome() · recalibrate_confidence()
        │
        ▼
Claude Opus 4.6  →  native tool use, proactive loop, no wrappers
        │
        ▼
Output  →  Daily briefing · Slack alert · Deal pipeline JSON · Web dashboard
```

---

## Key Capabilities

### Pricing & Conversion Decision Engine
Detects offer pricing drift using List-to-Sale Ratio (LSR) as an acceptance behavior proxy. When LSR ≤ 0.95, the system diagnoses the funnel stage-by-stage and generates a **Decision Packet** — not an insight, a packet ready to act on:

```
Issue:            Offer acceptance dropped 11.8% WoW
Severity:         HIGH — act within 24–72 hours
Evidence:         LSR at 0.95, pricing drifting outside observed acceptance behavior, DOM +6 days
Action:           Narrow offer band -2% to -4% in affected ZIPs by Friday
Financial Impact: ~10 homes/month at risk, $192k margin/month
Expected Outcome: +6–9% acceptance rate improvement within 2–3 weeks
Owner:            Pricing Team
```

### Capital-Light Deal Scoring
Ranks 100 acquisition opportunities by **Contribution Margin per day held** — the metric that matters for Opendoor's 2026 strategy. Full P&L per deal:

```
ARV − Acquisition − Renovation − Holding Costs − Selling Costs = CM
```

Supports semantic filters: `"capital-light opportunities"`, `"fast turn deals"`, `"high contribution margin"`.

### Severity Framework

| Severity | SLA | Response |
|----------|-----|----------|
| CRITICAL | 24 hours | Escalate to VP Acquisitions. Block new offers. |
| HIGH | 24–72 hours | Owner produces action plan by next business day |
| MEDIUM | 1 week | Flag for weekly review |
| LOW | Informational | Log and monitor |

### Self-Improving Feedback Loop
Every Decision Packet is logged with a predicted outcome. When the actual KPI is measured, prediction accuracy is computed and confidence weights are recalibrated automatically:

```
Decision Packet  →  log_recommendation()  →  record_action_taken()
        →  record_outcome()  →  recalibrate_confidence()  →  next briefing
```

### Pricing & Conversion Copilot (`copilot/`)
A separate deterministic detection pipeline — runs without an API key (`--mock` mode). Finds issues in synthetic data across 4 markets × 3 segments × 12 weeks. 49 tests passing.

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/ronokelishek/opendoor-agent.git
cd opendoor-agent
pip install -r requirements.txt

# 2. Add your API key
cp .env.example .env
# Add ANTHROPIC_API_KEY to .env

# 3. Interactive Q&A agent
py -m src.agent

# 4. Proactive daily briefing
py -m src.monitor

# 5. Pricing & Conversion Copilot (no API key needed)
py -m copilot.main --mock
```

---

## Example Agent Interactions

```
You: What markets should I be worried about right now?

  [calling: detect_anomalies]
  [calling: rank_all_markets]

Agent:
Charlotte and Dallas are flashing the same early-cycle warning pattern.
DOM is up 47% above average. Homes sold down 43% MoM.
List-to-sale ratio softening toward the 0.94 pause threshold.

Action: Tighten acquisition spreads in Charlotte immediately.
        Reduce buy-box volume. Monitor LSR weekly.
        If LSR < 0.94 next week — pause new offers.
```

```
You: Find me capital-light deals under $350k with ROI above 12%

  [calling: rank_top_100_deals(semantic_filter="capital-light opportunities")]

Agent:
27 deals meet the capital-light criteria.
Top opportunity: Phoenix · 2,100 sqft · cosmetic condition
  Acquisition: $298,000 · Reno: $31,000 · ARV: $412,000
  CM: $44,800 · ROI: 13.6% · Hold: 68 days · CM/day: $659
```

---

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| AI Model | Claude Opus 4.6 | Best reasoning + native tool use |
| Agent Framework | Anthropic Python SDK | No wrappers — direct API control |
| Data Processing | pandas | Standard, production-proven |
| Data Warehouse | Snowflake (Phase 2) | Opendoor's stack |
| Ingestion | AWS Kinesis + S3 + Glue | Real-time + batch paths |
| Scheduling | AWS EventBridge | Cron trigger for daily briefing |
| Language | Python 3.14 | |

---

## Project Structure

```
opendoor-agent/
├── src/
│   ├── agent.py                  ← Interactive Q&A agent
│   ├── monitor.py                ← Proactive daily briefing
│   └── tools/
│       ├── data_loader.py        ← Market metrics (summary, trend, anomalies)
│       ├── analyzer.py           ← Risk scoring engine (1–10 per market)
│       ├── deal_scout.py         ← Top 100 deals · ROI · P&L · reno estimates
│       ├── capital_light.py      ← CM forecast · inventory surges · semantic filters
│       ├── pricing_engine.py     ← Decision Engine · LSR · funnel · impact $
│       └── feedback_tracker.py   ← Prediction logging · outcome tracking · recalibration
├── copilot/                      ← Pricing & Conversion Copilot (standalone pipeline)
│   ├── data/                     ← Synthetic data generator (seed=42, reproducible)
│   ├── detection/                ← Deterministic issue detection (no LLM)
│   ├── agents/                   ← Claude reasoning layer (mock fallback)
│   └── reports/                  ← Executive markdown · JSON alerts · Slack summaries
├── agents/
│   ├── analytics-agent.yml       ← Agent definition (role, tools, output format)
│   └── monitor-agent.yml         ← Monitor agent definition
├── skills/
│   ├── market-briefing/          ← Daily market intelligence skill
│   ├── risk-analyzer/            ← 5-signal acquisition risk scoring
│   └── deal-scout/               ← ROI deal ranking skill
├── briefings/                    ← Auto-saved daily reports (markdown)
├── docs/
│   ├── portfolio.html            ← Portfolio showcase
│   ├── decision-engine.html      ← Decision Engine showcase
│   ├── production-architecture.html ← AWS production architecture
│   └── architecture.md           ← Full system documentation
├── .env.example
└── requirements.txt
```

---

## Why This Matters for Opendoor

Opendoor's 2026 strategy is **Capital-Light and AI-First**. The two metrics that matter:
1. **Contribution Margin** — net profit per deal after all costs. Floor: $30,000.
2. **Inventory Turn** — every extra day in possession erodes margin.

This system operationalizes both — finding the highest CM-per-day-deployed opportunities while flagging markets where rising inventory is silently compressing margins. It doesn't wait to be asked.

---

## How This Agent Directly Serves Opendoor's 2026 Strategy

### Problem 1: Every day a home sits = money lost
Opendoor owns the home. Mortgage, taxes, insurance, maintenance — ~$200–250/day per property. The 2026 Capital-Light strategy exists because they need to turn inventory faster.

**What the agent does:**
```
rank_top_100_deals()  →  sorts by CM/day, not just ROI
```
Instead of "which deal has the best profit?" it answers **"which deal makes the most money per day held?"** — that's the exact metric Opendoor 2026 runs on.

---

### Problem 2: Pricing drift kills conversion silently
In a volatile market, sellers are skittish. If Opendoor's offers drift even 3–4% above market, acceptance rate drops — but nobody notices for 2–3 weeks. By then, 10–15 deals are already lost.

**What the agent does:**
```
analyze_pricing_accuracy()  →  catches drift in real time
generate_pricing_actions()  →  tells you exactly what to adjust
estimate_business_impact()  →  "this is costing $192k/month right now"
```
It finds the problem **before the weekly review**, not after.

---

### Problem 3: Analysts answer questions. The agent asks them first.

| Traditional Analytics | This Agent |
|----------------------|------------|
| VP asks "how's Phoenix?" | Agent wakes up and says "Phoenix is broken, here's why, here's the cost, here's what to do" |
| Dashboard shows metrics | Agent interprets the metrics in cycle context |
| Report published Friday | Decision Packet ready Monday 6am |
| Analyst writes recommendation | Agent assigns owner, severity, and SLA |

---

### The Dollar Translation

Every signal becomes a number:

```
LSR drops 0.03  →  ~10 homes/month not closing  →  $192k margin at risk
DOM up 6 days   →  holding cost exposure compounds daily
Inventory surge →  capital deployed earning below CM floor
```

A VP of Acquisitions doesn't have time to read signals. They need **"act on this by Friday or it costs $192k."** That's what the agent produces.

---

### The One-Sentence Version

> Opendoor's margin lives in the spread between acquisition price and resale speed. This agent monitors both in real time, catches drift before it compounds, and tells the acquisitions team exactly what to do — in the same format they'd expect from a senior analyst, at 6am, every day, without being asked.

---

*Built for Opendoor's Senior Agentic Analytics Engineer role.*
