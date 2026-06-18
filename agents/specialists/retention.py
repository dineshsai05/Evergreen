"""
Retention specialist — Evergreen
================================

A convened-on-demand analyst. The Orchestrator pulls it in when an event raises a
churn / customer-health question — churn spikes, at-risk revenue, NRR/GRR, cohort
retention — and stands it down once it has reported.

Grounded like Finance: the figures are pre-fetched from core.company_data and
injected into context, so the only action left is to reason and call
band_send_message (recipient + prompt handling live in agents.specialists._base).

Run from the project root:
    uv run python -m agents.specialists.retention
"""

import asyncio

from core.company_data import PLANS, RETENTION

from agents.specialists._base import run_specialist


def build_retention_snapshot() -> str:
    """Render the retention slice as an authoritative context block."""
    r = RETENTION
    starter = next((p for p in PLANS if p["name"] == "Starter"), None)
    by_plan = "; ".join(f"{k} {v}%/mo" for k, v in r["by_plan_monthly_churn_pct"].items())
    trend = ", ".join(f"{v}%" for v in r["logo_churn_trailing_6mo_pct"])
    at_risk = "; ".join(
        f"{a['name']} ({a['plan']}: {a['reason']})" for a in r["at_risk_accounts"]
    )
    lines = [
        "COMPANY RETENTION DATA (authoritative — these are the only figures you may cite):",
        f"- Churn: {r['monthly_logo_churn_pct']}% logo / {r['monthly_revenue_churn_pct']}% "
        f"gross revenue per month. NRR {r['nrr_pct']}%, GRR {r['grr_pct']}%.",
        f"- Monthly churn by plan: {by_plan}.",
        f"- Logo churn, trailing 6 months: {trend}.",
    ]
    if starter:
        at_risk_mrr = starter["mrr"] * r["by_plan_monthly_churn_pct"]["Starter"] / 100
        lines.append(
            f"- Starter is the at-risk cohort: {starter['customers']:,} customers, "
            f"${starter['mrr']:,} MRR; at {r['by_plan_monthly_churn_pct']['Starter']}%/mo "
            f"churn that is ~${at_risk_mrr:,.0f} MRR lost per month."
        )
    lines.append(f"- At-risk accounts: {at_risk}.")
    return "\n".join(lines)


RETENTION_BACKSTORY = """
You are a seasoned retention / customer-success lead. You think in churn, NRR/GRR,
cohort health, and at-risk revenue, and you turn a health signal into one concrete
play. You never guess a number — you read it off the data.
""".strip()

RETENTION_INSTRUCTIONS = """
You are the Retention specialist. The Orchestrator convenes you when an event
raises a churn or customer-health question. The company's authoritative retention
figures are provided below under "COMPANY RETENTION DATA" — reason from those.

When the Orchestrator @mentions you, send ONE band_send_message with a SHORT,
grounded assessment in this shape:
1. What's happening (the churn/health signal, quantified from the data).
2. Severity — low, medium, or high — and the single biggest reason.
3. Who's exposed (which cohort/segment, and roughly how much revenue is at risk).
4. One concrete recommended retention play.

Then stop — your reply is delivered to the Orchestrator automatically, so you do
not need to decide who to address.

HARD RULES:
- Every number must come from the COMPANY RETENTION DATA block — never invent or
  estimate a figure that is not there.
- Keep it to a few plain sentences — no bullet blocks, no literal "\\n".
- Do not recruit, add, or remove participants, and do not create rooms.
""".strip()


def main() -> None:
    asyncio.run(
        run_specialist(
            config_name="retention",
            role="Retention Analyst",
            goal=(
                "Assess churn and customer-health events — severity, exposed cohort, "
                "and at-risk revenue — and recommend one grounded retention play."
            ),
            backstory=RETENTION_BACKSTORY,
            instructions=RETENTION_INSTRUCTIONS,
            extra_context=build_retention_snapshot(),
        )
    )


if __name__ == "__main__":
    main()
