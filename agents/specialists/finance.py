"""
Finance specialist — Evergreen
==============================

A convened-on-demand analyst. The Orchestrator pulls it in when an event raises
a financial question — revenue, pricing, churn cost, burn, runway — and stands it
down once it has reported.

What makes it a *real* specialist instead of a persona: it does not invent
figures. Every number in its answer comes from the company's data (mock today,
via core.company_data; swap to live billing/analytics later without touching the
agent wiring).

Why the figures are PRE-FETCHED and injected, not exposed as tools:
Band's CrewAI adapter delivers a reply to the room ONLY when the agent calls the
band_send_message tool during its run; the agent's CrewAI "final answer" is
discarded. When the agent has its own data tools, the model can satisfy the task
by calling those tools and emitting a final answer that never reaches the room.
So we compute the four figures in plain Python at startup and inject them into
context — the agent's only remaining action is to reason and call
band_send_message. Ratios are derived here so they can't drift from the base
figures.

Recipient handling (reporting only to the Orchestrator) and the suppression of
Band's conflicting prompt instructions both live in agents.specialists._base.

Run from the project root:
    uv run python -m agents.specialists.finance
"""

import asyncio

from core.company_data import CASH, MRR_TRAILING_6MO, PLANS, UNIT_ECONOMICS

from agents.specialists._base import run_specialist


# --------------------------------------------------------------------------- #
# Evidence. The numbers come ONLY from core.company_data — never from the model.
# Computed once at startup and injected into the agent's context.
# --------------------------------------------------------------------------- #
def revenue_snapshot() -> str:
    """Current revenue position: MRR, ARR, month-over-month growth, ARPU, and the trailing 6-month MRR trend."""
    mrr = sum(p["mrr"] for p in PLANS)
    paying = sum(p["customers"] for p in PLANS if p["mrr"] > 0)
    arpu = mrr / paying
    arr = mrr * 12
    t = MRR_TRAILING_6MO
    mom = (t[-1] - t[-2]) / t[-2] * 100
    trend = ", ".join(f"${v:,}" for v in t)
    return (
        f"MRR ${mrr:,} (ARR ${arr:,}), {mom:+.1f}% MoM. "
        f"ARPU ${arpu:.0f} across {paying:,} paying customers. "
        f"Trailing 6-month MRR: {trend}."
    )


def revenue_by_plan() -> str:
    """Revenue split across pricing plans: per-plan customer count, MRR, and share of total MRR (sizes exposure to a specific tier, e.g. the Starter plan)."""
    total = sum(p["mrr"] for p in PLANS) or 1
    parts = [
        f"{p['name']} (${p['price']}/mo): {p['customers']:,} customers, "
        f"${p['mrr']:,} MRR ({p['mrr'] / total * 100:.0f}% of MRR)"
        for p in PLANS
    ]
    return "Revenue by plan — " + "; ".join(parts) + "."


def unit_economics() -> str:
    """Unit economics: CAC, LTV, LTV:CAC ratio, gross margin, and CAC payback period."""
    u = UNIT_ECONOMICS
    ratio = u["ltv"] / u["cac"]
    return (
        f"CAC ${u['cac']}, LTV ${u['ltv']} (LTV:CAC {ratio:.1f}:1), "
        f"gross margin {u['gross_margin_pct']}%, CAC payback {u['cac_payback_months']} months."
    )


def burn_and_runway() -> str:
    """Cash position: monthly net burn, cash balance, and runway in months."""
    c = CASH
    runway = c["cash_balance"] / c["monthly_net_burn"]
    return (
        f"Net burn ${c['monthly_net_burn']:,}/mo, cash ${c['cash_balance']:,}, "
        f"runway ~{runway:.0f} months."
    )


def build_data_snapshot() -> str:
    """Render the full company data slice as a context block the agent reasons from."""
    return "\n".join(
        [
            "COMPANY FINANCIAL DATA (authoritative — these are the only figures you may cite):",
            f"- Revenue: {revenue_snapshot()}",
            f"- {revenue_by_plan()}",
            f"- Unit economics: {unit_economics()}",
            f"- {burn_and_runway()}",
        ]
    )


FINANCE_BACKSTORY = """
You are a seasoned startup finance lead — effectively a fractional CFO. You are
rigorous and numbers-first: you quantify the financial impact of anything before
you opine, and you think in MRR, margin, burn, and runway. You never guess a
number — you read it off the data.
""".strip()

FINANCE_INSTRUCTIONS = """
You are the Finance specialist. The Orchestrator convenes you when an event
raises a financial question (revenue, pricing, churn cost, burn, runway). The
company's authoritative figures are provided below under "COMPANY FINANCIAL
DATA" — reason directly from those numbers.

When the Orchestrator @mentions you, send ONE band_send_message containing a
SHORT, grounded assessment: quantify the impact using the real figures, then give
one concrete recommendation. Then stop — your reply is delivered to the
Orchestrator automatically, so you do not need to decide who to address.

HARD RULES:
- Every number in your answer must come from the COMPANY FINANCIAL DATA block —
  never invent, estimate, or recall a figure that is not there.
- Keep it to a few plain sentences — no bullet blocks, no literal "\\n".
- Do not recruit, add, or remove participants, and do not create rooms. Analyse
  and report; that is your whole job.
""".strip()


def main() -> None:
    asyncio.run(
        run_specialist(
            config_name="finance",
            role="Finance Analyst",
            goal=(
                "Quantify the financial impact of events on the company — revenue, "
                "pricing, burn, runway — and recommend grounded actions, always "
                "backed by real figures."
            ),
            backstory=FINANCE_BACKSTORY,
            instructions=FINANCE_INSTRUCTIONS,
            extra_context=build_data_snapshot(),
        )
    )


if __name__ == "__main__":
    main()
