---
name: condo-vs-house-intake
description: Use this skill when the user wants to compare condo vs house ownership costs. Drives the intake questionnaire, market fetches, parameter assembly, and analysis using cvh_cost.agent. Trigger phrases include "condo vs house", "should I buy a condo or a house", "compare ownership costs", "what's the long-run cost of...".
---

# Condo vs House Cost Analysis Intake

## When to use

The user is weighing one or more condos against one or more houses (or
just curious about long-run ownership cost) and wants numbers, not just
vibes. They've named at least one property OR are asking the comparison
in the abstract.

## How to drive the session

### Step 1 — Intake (batched)

Open `src/cvh_cost/agent/intake.py` and skim `QUESTION_BANK`. Pick the
questions relevant to what the user has already told you in chat — don't
re-ask facts they already volunteered.

Use the `AskUserQuestion` tool with **up to 4 questions per call**. Plan
2–3 batches max for the whole intake. Sections to cover, in priority
order:

1. **Horizon & discounting** — `horizon_years`, `discount_rate_source`
   (and `discount_rate_custom` only if they pick custom),
   `economic_mode`.
2. **Condo facts** — `condo_monthly_hoa`, `condo_hoa_growth`,
   `condo_hoa_covers`, plus reserves if the user mentioned them.
3. **House facts** — `house_price`, `house_value_growth`,
   `house_maintenance_rate`, `house_known_upcoming_events`, `region`.
4. **Risk & sims** — `risk_focus_percentile`, `mc_num_sims` (only if
   they care; otherwise default 10k is fine).

Skip optional questions unless the user gave a signal they want that
detail (e.g. they mentioned a special assessment → ask
`condo_special_assessment_history`).

After each batch, write the answers into the session:

```python
from cvh_cost.agent.assemble import set_intake
set_intake("condo_monthly_hoa", 520)
set_intake("condo_hoa_growth", "2.5%")  # coerce_answer handles the %
```

`set_intake` validates and coerces. If it raises, re-ask that question.

### Step 2 — Market

Always fetch before assembling, even though fixtures don't depend on
your call order:

```python
from cvh_cost.agent.market import (
    fetch_rate_curve, fetch_inflation_expectations,
    fetch_regional_benchmarks,
)
fetch_rate_curve()
fetch_inflation_expectations()
if "region" in get_session().intake:
    fetch_regional_benchmarks(get_session().intake["region"])
```

### Step 3 — Assemble & confirm

```python
from cvh_cost.agent.assemble import assemble_from_session
params = assemble_from_session()
```

Then summarize the assembled params back to the user in plain English,
with sources, e.g.:

> Here's what I'm using:
> - Horizon: 25 years (from your answer)
> - Discount rate: 2.0% real (10y Treasury 4.25% minus 10y breakeven 2.3%)
> - Condo HOA: $520/month, growing 2.5%/yr (from your answer)
> - House: $620k, growing 2%/yr, maintenance 1.3%/yr (regional benchmark)
>
> Anything off? Otherwise I'll run the simulation.

If the user wants to add events (roof, HVAC, etc), use:

```python
from cvh_cost.agent.assemble import add_event
add_event("house", name="roof", base_cost=14000, expected_year=18,
          timing_std_years=3, cost_vol=0.30)
```

### Step 4 — Run

```python
from cvh_cost.agent.analysis import (
    run_deterministic, run_monte_carlo, summarize_results,
)
det = run_deterministic()
mc = run_monte_carlo()  # default 10k sims, ~few seconds
print(summarize_results(mc["handle"]))
```

For a chart, `plot_results(mc["handle"], kind="diff")` returns a PNG
path — share it with the user.

### Step 5 — Narrate & offer one follow-up

Tell the user:
- The headline number (mean diff PV, equivalent monthly).
- The percentile they said they cared about (`risk_focus_percentile`).
- The probability the house costs more.
- One concrete sensitivity to explore next ("the result is sensitive to
  HOA growth — want me to stress that?"), not a menu of five.

To rerun with a tweak, use overrides — they don't mutate the session:

```python
mc2 = run_monte_carlo(overrides={"condo.fee_escalation_rate": 0.04})
```

## Things to avoid

- Don't ask one question at a time. Use `AskUserQuestion` batched.
- Don't make up market values. Always go through `cvh_cost.agent.market`.
- Don't run a 10k Monte Carlo before the user has confirmed the params.
- Don't dump the full numpy arrays from `MonteCarloResult` — use the
  summary in the tool return value, or `summarize_results(handle)`.
- Don't edit `cvh_cost/core/` or `cvh_cost/config/`. Math is frozen for
  this flow; only `cvh_cost/agent/` is in scope.

## Quick reference: question bank IDs

See `cvh_cost.agent.intake.QUESTION_BANK` for the live list. Categories:

- horizon: `horizon_years`, `discount_rate_source`, `discount_rate_custom`, `economic_mode`
- condo: `condo_price`, `condo_monthly_hoa`, `condo_hoa_growth`, `condo_hoa_covers`, `condo_reserve_balance`, `condo_reserve_contribution_rate`, `condo_special_assessment_history`
- house: `house_price`, `house_year_built`, `house_value_growth`, `house_maintenance_rate`, `house_known_upcoming_events`, `region`
- risk: `risk_focus_percentile`, `mc_num_sims`
