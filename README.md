# Housing Decision Engine

Present value comparison engine for housing decisions — rent vs condo vs house —
with employment cash flow modeling, real estate market scenario analysis,
and an MCP server so Claude can run comparisons directly.

## Features

- **3-way PV comparison** — rent / condo / house (rent coming in S3)
- **Deterministic + Monte Carlo** — fixed-parameter estimate + full uncertainty distribution
- **Employment cash flow** — model income trajectories and pay-drop events (S3)
- **Market scenario analysis** — real estate price shocks, rate sensitivity (S4)
- **MCP server** — Claude-callable tools, no notebooks required (S2)
- **CLI** — `hde` command for standalone use
- **YAML scenarios** — config files for reproducible comparisons

## Installation

```bash
git clone <repo>
cd housing-decision-engine
uv sync --extra dev
```

## Quick Start

```bash
# Run a scenario
uv run hde examples/basic_config.yaml

# Deterministic only
uv run hde examples/basic_config.yaml --no-monte-carlo

# Summary line only
uv run hde examples/basic_config.yaml --quiet
```

## MCP Server

*Coming in Session 2.* Claude will be able to call housing comparison tools
directly via MCP — no YAML file required.

## As a Library

```python
from hde.models import CondoParams, HouseParams, SimulationParams, EconomicParams
from hde.deterministic import compute_deterministic
from hde.monte_carlo import run_monte_carlo

condo = CondoParams(monthly_fee=400, fee_escalation_rate=0.02)
house = HouseParams(initial_value=400_000, annual_maintenance_rate=0.015)
sim = SimulationParams(years=20, discount_rate=0.03)
econ = EconomicParams()

det = compute_deterministic(condo, house, sim, econ)
mc = run_monte_carlo(condo, house, sim, econ)

print(f"Deterministic difference: ${det.diff_pv:,.0f}")
print(f"P(House more expensive): {mc.prob_house_more_expensive:.1%}")
```

## Configuration

YAML scenario files. See `examples/` for templates.

```yaml
years: 20
discount_rate: 0.03

condo:
  monthly_fee: 400
  fee_escalation_rate: 0.02

house:
  initial_value: 400000
  annual_maintenance_rate: 0.015
  events:
    - name: "roof"
      base_cost: 12000
      expected_year: 15
      timing_std_years: 2
      cost_vol: 0.25

simulation:
  num_sims: 10000
  random_seed: 42
  house_maintenance_vol: 0.30
  condo_fee_vol: 0.05
```

## Project Structure

```
src/hde/            # Core engine
  models.py         # Dataclasses: params + results
  pv.py             # PV utility functions
  deterministic.py  # Deterministic engine
  monte_carlo.py    # Monte Carlo engine
  config.py         # YAML config loader
  reporting.py      # Reports + plots
  cli.py            # CLI entry point
mcp_server/         # MCP server (S2 — coming)
examples/           # Scenario YAML files
tests/              # Test suite (76 tests)
docs/
  roadmaps/         # Project roadmaps
  specs/            # Session design docs
  reference/        # Architecture + API docs
```

## Tests

```bash
uv run python -m pytest
```

## Roadmap

See `docs/roadmaps/2026-06-07_housing-decision-engine.md` for the full arc:
- S1 ✅ Repo foundation (rename, uv, AGENTS.md, CLAUDE.md)
- S2 MCP server
- S3 Rent option + employment cash flow
- S4 Market scenario layer
