"""
Company data store — Evergreen
==============================

This is the shared, single source of truth that specialists read when they need
evidence. It stands in for the real systems of record (billing, analytics, the
cap table) that specialists will query in production.

The STRUCTURE is real; the NUMBERS are mock and hardcoded for now. To make a
specialist's analysis reflect a different situation, edit the values here — or,
later, replace these constants with live API calls (Stripe, PostHog, …) without
touching any agent. Ratios (ARPU, LTV:CAC, runway) are intentionally NOT stored;
the tools derive them, so the figures can never drift out of sync.

All numbers describe one fictional SaaS form-builder — the startup this room
owns — and are internally consistent.

Place this file at:  core/company_data.py
"""

COMPANY = {
    "name": "our company",
    "product": "SaaS online form builder",
    "as_of": "2026-06",
    "currency": "USD",
}

# Pricing tiers and the book of business on each.
PLANS = [
    {"name": "Free",     "price": 0,   "customers": 3200, "mrr": 0},
    {"name": "Starter",  "price": 19,  "customers": 1150, "mrr": 21850},
    {"name": "Pro",      "price": 49,  "customers": 380,  "mrr": 18620},
    {"name": "Business", "price": 149, "customers": 52,   "mrr": 7748},
]

# Last 6 months of total MRR (oldest -> newest); newest equals the sum of PLANS.
MRR_TRAILING_6MO = [39800, 41600, 43500, 45200, 46600, 48218]

UNIT_ECONOMICS = {
    "cac": 180,
    "ltv": 720,
    "gross_margin_pct": 82,
    "cac_payback_months": 7,
}

CASH = {
    "monthly_net_burn": 62000,
    "cash_balance": 740000,
}