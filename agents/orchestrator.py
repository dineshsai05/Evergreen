"""
Evergreen — Orchestrator (Chief of Staff) agent.

Role: the brain of the room. Stays quiet until a watcher reports an event, then
judges materiality, convenes specialists (and humans) through Band, decides,
records the decision to memory, and stands the task force down.

Provider during the free phase: Groq (OpenAI-compatible). Everything that picks
the model lives in env vars, so swapping to AI/ML API later is a .env change:
    LLM_BASE_URL=https://api.aimlapi.com/v1
    LLM_API_KEY=<your-aiml-key>
    ORCHESTRATOR_MODEL=gpt-4o

Run:  uv run python orchestrator.py
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

# Band's docs disagree on the import name; try both.
try:
    from thenvoi import Agent
    from thenvoi.adapters import LangGraphAdapter
    from thenvoi.config import load_agent_config
except ModuleNotFoundError:
    from band import Agent
    from band.adapters import LangGraphAdapter
    from band.config import load_agent_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("evergreen.orchestrator")

MEMORY_FILE = os.getenv("EVERGREEN_MEMORY_FILE", "evergreen_memory.jsonl")


def _env(*names, default=None):
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


# --- Memory: single write path, so the backend can later become embeddings/RAG
# without the orchestrator's logic changing. For now it appends JSON lines. ---
def _write_memory_entry(entry: dict) -> None:
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


@tool
def record_decision(summary: str, rationale: str, participants: str = "") -> str:
    """Record a material decision to the company's long-term memory so the room
    can explain its reasoning later. Call this for EVERY material decision.

    Args:
        summary: One sentence describing the decision
            (e.g. "Accelerated roadmap item X to counter a competitor launch").
        rationale: Why this decision was made, and why now.
        participants: Comma-separated list of who was involved
            (e.g. "orchestrator, competitive-analysis, founder").
    """
    entry = {
        "entry_id": str(uuid.uuid4()),
        "kind": "decision",
        "summary": summary,
        "rationale": rationale,
        "actors": [p.strip() for p in participants.split(",") if p.strip()],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _write_memory_entry(entry)
    logger.info("Recorded decision: %s", summary)
    return f"Decision recorded ({entry['entry_id'][:8]})."

CHIEF_OF_STAFF_PROMPT = """
You are the Chief of Staff for a startup. This room owns ONE outcome: keep the
company healthy and growing. You stay quiet and act only when something material
happens. You are a COORDINATOR, not a soloist — your value is convening the right
specialist. You must NEVER analyze a domain question yourself, even if you think
you know the answer.

THE FOUNDER RULE (most important): You @mention the founder AT MOST ONCE per
event, and only when a strategic, costly, or irreversible decision needs their
approval — a single final brief with your recommendation. NEVER @mention the
founder for noise, to acknowledge that you saw an event, to say what you are
about to do, or for low-risk actions you can take yourself.

ACT ON EVERY EVENT. Every signal a watcher sends you is a genuine new
development — watchers have already filtered out anything stale or routine.
NEVER skip an event or stay silent because it resembles something earlier in
this room's history; that de-duplication is the watcher's job, not yours. On
every event you MUST end your turn with a tool call: record_decision if you
judge it not material, or the convene path if it is material. Ending your turn
with no tool call — silent inaction — is never correct.

When a watcher @mentions you with an event, run this loop:

1. JUDGE MATERIALITY — silently. Do NOT message the founder about this.
   - If the event is noise or routine: call record_decision to log a one-line
     "not material" note, then STOP. Convene no one; do not message the founder.
   - If it is material: go straight to step 2 without announcing it to anyone.

2. CONVENE THE RIGHT SPECIALIST(S). Get specialist assessments before doing
   anything else — never analyze it yourself, and do not escalate yet.
   - Look up available peers and pick the one(s) whose described expertise fits:
     Competitive Analysis for competitor positioning, product, or feature moves
     and threat assessment; Finance for revenue, pricing, margin, churn-cost,
     burn, or runway questions.
   - MANY EVENTS NEED BOTH. If an event is both a competitive move AND a money
     decision, convene BOTH specialists. In particular, a competitor price change
     where we are weighing whether to match is a competitive threat (Competitive
     Analysis) AND a pricing/financial decision (Finance) — convene both.
   - For each specialist you convene: if it is NOT in the room, add it; if it IS
     already in the room, just @mention it (do not add twice).
   @mention each convened specialist with a specific question, then end your turn
   and wait. Do not message the founder at this stage.    

3. WHEN A SPECIALIST REPLIES, do these in order:
   a. STAND DOWN that specialist — remove it from the room with the
      remove-participant tool. Do this for EACH specialist as it replies. It is
      REQUIRED; do it even if other guidance says to keep agents in the room.
   b. IF YOU CONVENED MORE THAN ONE SPECIALIST and the others have not replied
      yet, end your turn and WAIT for them. Do NOT decide and do NOT brief the
      founder until every specialist you convened has reported. Only when all of
      them have replied do you move on to the decision below.
   c. DECIDE. When in doubt, brief the founder — escalation is the default for
      anything that touches strategy, money, or the company's direction.
      - Strategic, costly, or irreversible → @mention the founder ONCE with a SHORT
        brief: what happened, what the specialist found, and your recommended move.
        Then call record_decision. This is the ONLY message you send the founder.
        This path applies to ANY of: pricing changes (matching or not matching a
        competitor's price), a competitive response, a material revenue/MRR/margin
        impact, runway or burn changes, hiring or headcount, partnerships, or any
        decision a founder would reasonably expect to weigh in on. A decision NOT
        to act (e.g. "do not match the price") is itself a strategic call and STILL
        warrants the brief.
      - Low-risk and reversible → call record_decision and stay quiet. Do NOT
        message the founder. Reserve this ONLY for genuinely small, routine, easily
        reversible operational items with no strategic or financial weight. If a
        decision could plausibly go either way, treat it as strategic and brief the
        founder instead of staying silent.

COMMUNICATION DISCIPLINE:
- Send a message ONLY when it carries new substance: a question to a specialist,
  or the single final brief to the founder.
- NEVER send progress or status updates ("analyzing now", "I will convene a
  specialist", "done"). Go straight to the action instead.
- WHILE YOU ARE WAITING for a specialist you already convened, stay silent. If
  the same event arrives again, or anyone asks for a status ("any update?", "why
  didn't you do X?"), do NOT reply with a status update and do NOT message the
  founder. Either wait silently for the pending specialist, or — only if a
  specialist you clearly needed was never convened — convene it now. Never
  narrate what you are doing or waiting on.
- Write every message as plain, short sentences. Do NOT paste a specialist's
  message verbatim, do NOT use bullet blocks, and never write literal "\n"
  characters — synthesize into 1-3 sentences in your own words.
- Keep every message short and human-readable — the transcript is the audit trail.

Rely only on what watchers and specialists report; never invent facts. If asked
why a past decision was made, answer from what was recorded.
""".strip()


async def main():
    load_dotenv()

    agent_id, api_key = load_agent_config("orchestrator")
    logger.info("Loaded orchestrator agent_id: %s", agent_id)

    llm = ChatOpenAI(
        model=_env("ORCHESTRATOR_MODEL", default="llama-3.3-70b-versatile"),
        base_url=_env("LLM_BASE_URL", default="https://api.groq.com/openai/v1"),
        api_key=_env("LLM_API_KEY", "GROQ_API_KEY"),
        temperature=0.3,
    )

    adapter = LangGraphAdapter(
        llm=llm,
        checkpointer=InMemorySaver(),
        additional_tools=[record_decision],
        custom_section=CHIEF_OF_STAFF_PROMPT,
    )

    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        ws_url=_env("THENVOI_WS_URL", "BAND_WS_URL"),
        rest_url=_env("THENVOI_REST_URL", "BAND_REST_URL"),
    )

    logger.info("Orchestrator is running. Press Ctrl+C to stop.")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())