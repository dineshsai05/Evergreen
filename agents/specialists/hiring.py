"""
Hiring specialist — Evergreen
=============================

A convened-on-demand analyst. The Orchestrator pulls it in when an event raises a
hiring / org-capacity question — a key departure, a stalled pipeline, attrition,
headcount plan vs actual — and stands it down once it has reported.

Grounded like Finance: the figures are pre-fetched from core.company_data and
injected into context, so the only action left is to reason and call
band_send_message (recipient + prompt handling live in agents.specialists._base).

Run from the project root:
    uv run python -m agents.specialists.hiring
"""

import asyncio

from core.company_data import HIRING

from agents.specialists._base import run_specialist


def build_hiring_snapshot() -> str:
    """Render the hiring slice as an authoritative context block."""
    h = HIRING
    gap = h["headcount_plan"] - h["headcount_actual"]
    reqs = "; ".join(
        f"{r['role']} ({r['function']}, open {r['days_open']}d, "
        f"pipeline {r['pipeline']['applied']}→{r['pipeline']['screen']}→"
        f"{r['pipeline']['onsite']}→{r['pipeline']['offer']} "
        f"applied/screen/onsite/offer)"
        for r in h["open_reqs"]
    )
    return "\n".join(
        [
            "COMPANY HIRING DATA (authoritative — these are the only figures you may cite):",
            f"- Headcount: {h['headcount_actual']} actual vs {h['headcount_plan']} plan "
            f"({gap} to hire). Monthly attrition {h['monthly_attrition_pct']}%, "
            f"average time-to-fill {h['avg_time_to_fill_days']} days.",
            f"- Open reqs: {reqs}.",
        ]
    )


HIRING_BACKSTORY = """
You are a seasoned head of talent / people-ops lead. You think in pipeline health,
time-to-fill, attrition, and headcount plan vs actual, and you turn an org signal
into one concrete action. You never guess a number — you read it off the data.
""".strip()

HIRING_INSTRUCTIONS = """
You are the Hiring specialist. The Orchestrator convenes you when an event raises a
hiring or org-capacity question. The company's authoritative hiring figures are
provided below under "COMPANY HIRING DATA" — reason from those.

When the Orchestrator @mentions you, send ONE band_send_message with a SHORT,
grounded assessment in this shape:
1. What's happening (the hiring/capacity signal, quantified from the data).
2. Severity — low, medium, or high — and the single biggest reason.
3. Who's exposed (which function/role, and the capacity or pipeline gap).
4. One concrete recommended action.

Then stop — your reply is delivered to the Orchestrator automatically, so you do
not need to decide who to address.

HARD RULES:
- Every number must come from the COMPANY HIRING DATA block — never invent or
  estimate a figure that is not there.
- Keep it to a few plain sentences — no bullet blocks, no literal "\\n".
- Do not recruit, add, or remove participants, and do not create rooms.
""".strip()


def main() -> None:
    asyncio.run(
        run_specialist(
            config_name="hiring",
            role="Hiring Analyst",
            goal=(
                "Assess hiring and org-capacity events — severity, exposed function, "
                "and the pipeline/headcount gap — and recommend one grounded action."
            ),
            backstory=HIRING_BACKSTORY,
            instructions=HIRING_INSTRUCTIONS,
            extra_context=build_hiring_snapshot(),
        )
    )


if __name__ == "__main__":
    main()
