# Opendoor Agentic Analytics Assistant

## Project Purpose
An AI agent that proactively monitors real estate market data, surfaces actionable
insights, and answers natural language questions — demonstrating the analytics-to-action
pipeline for Opendoor's Agentic Analytics Engineer role.

## Tech Stack
- Python 3.14
- Anthropic Claude API (claude-opus-4-6) — native tool use, no wrappers
- pandas for data processing
- python-dotenv for secure config

## Architecture
- `src/agent.py` — interactive Q&A agent (natural language → tool calls → insight)
- `src/monitor.py` — proactive daily briefing (no question needed)
- `src/tools/data_loader.py` — 3 data tools: summary, trend, anomalies
- `src/tools/analyzer.py` — risk scoring engine (1-10 per market)
- `agents/` — agent definitions (role, tools, output format)
- `skills/` — skill definitions (when to use, how it works)
- `briefings/` — auto-saved daily reports

---

## Workflow Orchestration

### 1. Plan Before Building
- For any non-trivial change (new tool, new agent, new output format): plan first
- If something breaks: STOP, re-read the error, re-plan — don't keep pushing
- Write what you expect the output to look like before writing the code

### 2. Subagent Strategy
- Use subagents to keep the main agent context clean
- Offload data fetching to tools — one tool per responsibility
- Each tool must do one thing and return a structured dict

### 3. Self-Improvement Loop
- After any correction: update `docs/lessons.md` with the pattern
- Write rules that prevent the same mistake happening again
- Review lessons at the start of each session

### 4. Verification Before Done
- Never mark a task complete without running the code and checking output
- Ask: "Would a senior data engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky, implement the clean solution instead
- Don't over-engineer — but don't leave technical debt either

### 6. Autonomous Bug Fixing
- When given a bug: read the full traceback before touching code
- Point at the root cause, not the symptom
- Zero hand-holding required — fix it and verify it

---

## Task Management

1. **Plan First** — write what needs to change and why before coding
2. **Verify Plan** — check it makes sense before implementing
3. **Track Progress** — mark tasks complete as you go
4. **Explain Changes** — one-line summary of what changed and why
5. **Capture Lessons** — update `docs/lessons.md` after any correction

---

## Core Principles

- **Simplicity First** — make every change as simple as possible
- **No Laziness** — find root causes, no temporary fixes
- **Minimal Impact** — changes should only touch what is necessary
- **Real Data Only** — never guess or hallucinate numbers; always call a tool
- **Action-Oriented Output** — every response must end with a recommended action

---

## Security
- Never hardcode API keys — always use `.env`
- `.env` is gitignored — never commit secrets
- All tool inputs are validated before use

## Conventions
- Tools return structured dicts (JSON-serializable)
- Agent responses always follow: Insight → Evidence → Recommended Action
- Risk scores are numeric (1-10) for ranking and threshold logic
- Briefings are saved as markdown in `briefings/`
