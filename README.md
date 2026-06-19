# Evergreen

**Assign an AI _room_ to an _outcome_, and it owns that outcome for its whole lifetime** —
watching continuously, waking on real-world events, convening the right specialists and
humans, recording every decision and the reasoning behind it, then going back to watching.

Most agent systems are vending machines: request → burst of work → output → off. Evergreen
inverts that. You don't give it a task; you give it an **outcome to own**.

Locked use case: a **Startup Operating System** ("chief-of-staff"). The room owns one
outcome — *keep the company healthy and growing* — and runs indefinitely.

**📊 [Presentation deck (PDF)](./Evergreendeck.pdf)** · Built on **Band** (coordination) +
**LangGraph** + **CrewAI** + **AI/ML API** · MIT-licensed.

## The three pillars

Evergreen is defined by three non-negotiable properties:

1. **Persistent** — a room stays alive over weeks/months; its state survives restarts.
2. **Event-driven** — it reacts the moment something happens, not when prompted.
3. **Institutional memory** — it remembers every signal, decision, and rationale, and can
   answer *"why did we decide X?"* months later.

> **Litmus test:** if the system would still work after deleting the simulated clock and the
> memory, it has degraded into a one-shot pipeline. That's failure. All three pillars are
> demonstrated end-to-end (see [Status](#status)).

**The differentiator — _dynamic convening_:** per event, the orchestrator assembles a
situation-specific task force (the right specialists + the right humans) via Band's
add/remove-participant primitives, then stands it down. The room persists and remembers;
only the roster flexes.

## How it works — the funnel

Three tiers of agents, each deeper and more expensive than the last:

| Tier | Role | Job | Organized by |
|------|------|-----|--------------|
| **Watchers** | detection | "Did something happen?" — sensors, never analyze or recommend | data source |
| **Orchestrator** | triage | "Does it matter, and who should look?" — routes, never analyzes | (the single router) |
| **Specialists** | analysis | "What does it mean, how bad, what do we do?" — deep, on-demand | expertise |

Watchers and specialists do **not** map 1:1 — the orchestrator is the router, and one signal
can fan out to several specialists (e.g. a competitor price cut → Competitive Analysis **and**
Finance). Specialists never watch or self-trigger; they sit dormant until convened and report
only to the orchestrator.

```
 Watcher ──event──▶ Orchestrator ──convene──▶ Specialist(s)
 (sensor)           (triage)      ◀──report───  (analysis)
                       │  └── stand down ──▶ (remove from room)
                       └── record decision ──▶ memory
                       └── one brief ───────▶ Founder (human)
```

**Cross-framework by design:** the **Orchestrator** runs on **LangGraph** (model `gpt-4o`);
the **Specialists** run on **CrewAI** (model `gpt-4o-mini`). **[Band](https://band.ai)** is
the coordination spine — remove it and the system collapses (that's the goal). All reasoning
is powered by the **[AI/ML API](https://aimlapi.com)** (OpenAI-compatible).

### Agents

- **Orchestrator** (Chief of Staff) — the only coordinator. Judges materiality, convenes
  specialists, stands them down, records decisions, escalates to the founder at most once per
  event. Tools: `record_decision`, `recall_decisions`.
- **Specialists** (convened on demand, report only to the orchestrator):
  - **Competitive Analysis** — persona; threat assessment of competitor moves.
  - **Finance** — grounded; revenue, pricing, margin, burn, runway.
  - **Retention** — grounded; churn, customer health, NRR/GRR, at-risk revenue.
  - **Hiring** — grounded; pipeline, attrition, time-to-fill, headcount.
  - Grounded specialists **pre-fetch real figures and inject them into context** (never
    model-invented), all on a shared base (`agents/specialists/_base.py`) that forces the
    reply recipient and suppresses Band's conflicting prompt instructions in code.
- **Market Watcher** — standing, LLM-free REST detector, driven by the simulated clock.
- **Founder** — a human participant (the escalation target / approver), not an agent.

### Infrastructure

- **Memory** — `evergreen_memory.jsonl`, an append-only decision log (`record_decision`);
  `recall_decisions` reads it back. Memory is **global** (institutional), not per-room.
- **Simulated clock** — `clock/sim_clock.py` maps real seconds to "sim-days" and persists the
  current day, so long-running behavior is visible and resumes across restarts.

## Status

Built and **verified live in a Band room**:

- ✅ Materiality gate (noise → silently recorded, no convene).
- ✅ Full **fan-out** cascade (convene multiple specialists → grounded replies → stand each
  down → one synthesized founder brief).
- ✅ Event-driven over **sim time** (watcher idle for "days", fires scheduled events).
- ✅ **Persistence across restart** (memory + sim-day survive; no event replay).
- ✅ **Memory recall** — answers "why did we decide X?" from durable memory, across rooms and
  restarts, with no specialist convened.

Deferred (out of hackathon scope): real watcher integrations (the watcher→orchestrator
interface is just a posted event, so swapping the feed changes nothing downstream).

See **[EVERGREEN_CONTEXT.md](EVERGREEN_CONTEXT.md)** for the full architecture, the hard-won
Band SDK facts, and the build log, and **[EVERGREEN_NEXT.md](EVERGREEN_NEXT.md)** for the
roadmap and working principles.

## Setup

Requires **Python 3.13+** and **[uv](https://docs.astral.sh/uv/)**.

1. **Install dependencies**
   ```bash
   uv sync
   ```

2. **Create the agents on [Band](https://band.ai)** under one account, each with a clear
   description (the orchestrator routes by peer description): `Orchestrator`, `Competitive
   Analysis`, `Finance`, `Retention`, `Hiring`, `Market Watcher`. Create a room and add the
   **Orchestrator** and **Market Watcher** to it (specialists are convened on demand).

3. **Configure** (both files are gitignored — they hold live keys):
   ```bash
   cp .env.example .env                           # AI/ML + Band URLs, room id, clock config
   cp agent_config.example.yaml agent_config.yaml # per-agent {agent_id, api_key}
   ```
   Fill in your AI/ML API key, the room UUID, and each agent's id/key.

## Run

Each in its own terminal, from the project root. **Start the orchestrator and specialists
first and let them connect** (Band does not queue @mentions for offline agents), then the
watcher:

```bash
uv run python -m agents.orchestrator
uv run python -m agents.specialists.competitive_analysis
uv run python -m agents.specialists.finance
uv run python -m agents.specialists.retention
uv run python -m agents.specialists.hiring
uv run python -m agents.watchers.market_watcher
```

The Market Watcher then fires its scheduled events on their sim-days. You can also drive the
room manually as the founder — post an `@Orchestrator …` message. Examples:

```
@Orchestrator [event from market-watcher] Typeform cut their Starter plan price 30%. We're weighing whether to match it.
@Orchestrator [event from market-watcher] Monthly churn jumped from 2% to 5%, mostly on the Starter plan.
@Orchestrator why did we decide not to match Typeform's price cut?
```

**Verify a run** via the agent logs + `evergreen_memory.jsonl` + the Band UI (the agent REST
`messages` endpoint is a work queue, not a transcript).

## Project structure

```
agents/
  orchestrator.py                 # LangGraph; record_decision + recall_decisions
  specialists/
    _base.py                      # shared base: forced recipient + prompt-conflict fix
    competitive_analysis.py       # persona
    finance.py  retention.py  hiring.py   # grounded (pre-fetch + inject)
  watchers/
    market_watcher.py             # REST, send-only; clock-driven schedule
clock/
  sim_clock.py                    # real secs -> sim-days, persisted
core/
  company_data.py                 # mock "company profile" (the data specialists read)
evergreen_memory.jsonl            # decision log (gitignored runtime state)
EVERGREEN_CONTEXT.md              # full context + Band SDK facts + build log
EVERGREEN_NEXT.md                 # roadmap + working principles
```

## Tech stack

[Band](https://band.ai) (coordination) · [LangGraph](https://www.langchain.com/langgraph)
(orchestrator) · [CrewAI](https://www.crewai.com/) (specialists) ·
[AI/ML API](https://aimlapi.com) (reasoning) · Python 3.13 · uv.

## Presentation

The pitch deck is in the repo: **[`Evergreendeck.pdf`](./Evergreendeck.pdf)**.

## License

[MIT](./LICENSE) © 2026 Dinesh Sai Rayapati.
