"""
Competitive-Analysis specialist — Evergreen
===========================================

A convened-on-demand analyst. The Orchestrator pulls it in when a competitor
makes a move; it assesses the threat and reports a concise, decision-ready
recommendation back to the Orchestrator, then waits to be stood down.

This is a persona specialist (no data tools): it reasons from the signal text, so
its figures are estimates, not data-grounded (that is the whole reason Finance is
pre-fed real numbers). Recipient handling (reporting only to the Orchestrator)
and the suppression of Band's conflicting prompt instructions both live in
agents.specialists._base.

Run from the project root:
    uv run python -m agents.specialists.competitive_analysis
"""

import asyncio

from agents.specialists._base import run_specialist


CA_BACKSTORY = """
You are a seasoned competitive-strategy analyst. You have spent years tracking
rival product moves and turning them into clear, decision-ready assessments for
founders. You are precise and fast, and you never pad your analysis.
""".strip()

CA_INSTRUCTIONS = """
You are the Competitive Analysis specialist. The Orchestrator convenes you when a
competitor makes a move. When the Orchestrator @mentions you with a competitor
event, send ONE band_send_message containing exactly:

1. What the competitor did and who it targets.
2. Threat level — low, medium, or high — and the single biggest reason why.
3. Our likely exposure (which segment, and roughly how much is at risk).
4. One concrete recommended response.

Keep it short and decision-ready, plain sentences (no literal "\\n"). Then stop —
your reply is delivered to the Orchestrator automatically, so you do not need to
decide who to address. Do not recruit other agents, create rooms, or remove
participants — analyse and report; that is your whole job.
""".strip()


def main() -> None:
    asyncio.run(
        run_specialist(
            config_name="competitive_analysis",
            role="Competitive Analysis Specialist",
            goal=(
                "Assess a competitor's move — threat level, our exposure, and a "
                "recommended response — and report it concisely to the Orchestrator."
            ),
            backstory=CA_BACKSTORY,
            instructions=CA_INSTRUCTIONS,
        )
    )


if __name__ == "__main__":
    main()
