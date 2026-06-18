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

# Retention / customer-health slice. Consistent with PLANS: the Starter cohort is
# the largest by logo count and the cheapest, and it churns hardest — so it's the
# at-risk segment. Logo churn has crept up over the trailing 6 months.
RETENTION = {
    "monthly_logo_churn_pct": 3.2,
    "monthly_revenue_churn_pct": 2.8,   # gross revenue churn
    "nrr_pct": 102,                     # expansion offsets churn (net revenue retention)
    "grr_pct": 96,                      # gross revenue retention
    "by_plan_monthly_churn_pct": {"Starter": 4.5, "Pro": 1.6, "Business": 0.8},
    "logo_churn_trailing_6mo_pct": [2.6, 2.8, 2.9, 3.0, 3.1, 3.2],  # oldest -> newest
    "at_risk_accounts": [
        {"name": "Northwind Co", "plan": "Pro", "reason": "no logins in 21 days"},
        {"name": "Acme Forms", "plan": "Business", "reason": "usage down 40% MoM, support tickets up"},
    ],
}

# Hiring / org-capacity slice. headcount gap (plan - actual) matches the open reqs.
HIRING = {
    "headcount_actual": 18,
    "headcount_plan": 21,
    "monthly_attrition_pct": 2.1,
    "avg_time_to_fill_days": 48,
    "open_reqs": [
        {"role": "Senior Backend Engineer", "function": "Engineering",
         "days_open": 52, "pipeline": {"applied": 40, "screen": 8, "onsite": 3, "offer": 1}},
        {"role": "Product Designer", "function": "Product",
         "days_open": 30, "pipeline": {"applied": 25, "screen": 5, "onsite": 2, "offer": 0}},
        {"role": "Customer Success Lead", "function": "Customer Success",
         "days_open": 21, "pipeline": {"applied": 18, "screen": 4, "onsite": 1, "offer": 0}},
    ],
}