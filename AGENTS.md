# Housing Decision Engine — AGENTS.md

Canonical operational rules for this repo. Claude reads this first.

## What This Repo Is

Present value comparison engine for housing decisions: rent vs condo vs house.
Extends to employment cash flow modeling and real estate market scenario analysis.
Surfaces as an MCP server — Claude calls tools directly, no notebooks needed.

## Revenue stream / context

Personal financial tooling (own use). Not fund money-path — no VRP, no equity rebalance.
`money-path: no` on all work in this repo.

## Package layout

```
src/hde/            # Core engine (Python package)
  models.py         # Dataclasses: params + results (incl. ComparisonSpec, RentParams, IncomeParams)
  pv.py             # Pure PV utility functions
  deterministic.py  # Deterministic PV engine (compute_deterministic(spec: ComparisonSpec))
  monte_carlo.py    # Monte Carlo simulation engine (run_monte_carlo(spec: ComparisonSpec))
  config.py         # YAML config loader (load_config_dict → ComparisonSpec)
  reporting.py      # Text reports + matplotlib figures
  cli.py            # CLI entry point (hde)
mcp_server/         # MCP server (FastMCP, stdio transport)
  main.py           # FastMCP entry point + @mcp.tool wrappers
  registry.py       # In-memory ScenarioEntry store (spec: ComparisonSpec)
  tools.py          # 6 tool implementations + serialization helpers
tests/              # pytest suite (151 tests)
examples/           # Example YAML scenario configs
docs/
  roadmaps/         # Roadmap spines (do not edit arc spine)
  specs/            # Design docs produced by brainstorming sessions
  reference/        # Architecture, API contract, config schemas (formerly context/)
  archive/notebooks/# Deprecated Jupyter notebooks
```

## Entry points

```bash
# CLI
uv run hde <config.yaml> [--no-monte-carlo] [--quiet]

# Tests
uv run python -m pytest

# MCP server
uv run hde-mcp                         # stdio transport (Claude Code)
# Register with Claude Code:
# claude mcp add hde -- uv --directory /home/mm-mike/ai_system/projects/housing-decision-engine run hde-mcp
```

## Development setup

```bash
uv sync --extra dev
uv run python -m pytest
uv run hde examples/basic_config.yaml
```

## Key design decisions (stable)

- **ComparisonSpec** is the single input bundle for all engines — replaces the old `(condo, house, sim, econ)` 4-tuple. All options (condo, house, rent, income) are Optional; at least one of condo/house/rent must be present.
- **3-way comparison** — rent, condo, house are all first-class options. Rent PV includes `invested_dp_benefit_pv = dp × (1+r_inv)^N / (1+dr)^N` (negative, reduces total cost).
- **Affordability layer** — `IncomeParams` + `PayDropEvent` produce per-year housing-cost/income ratios returned inline in `run_comparison` as `"affordability"` key.
- **Deterministic + Monte Carlo** run as separate engines; deterministic is the sanity check, MC is the uncertainty surface.
- **YAML config** is the input contract — scenarios are files, not code. `load_config_dict` returns `ComparisonSpec`.
- **Pure functions** throughout — no global state, seeded RNG for reproducibility.
- **MCP tools** wrap the existing engine; no engine logic in the MCP layer.
- **Session registry** (`registry.py`) is in-process, process-scoped — cleared on server restart. Stores `spec: ComparisonSpec` (not a 4-tuple).
- **MC numpy arrays** never cross the MCP boundary; only `MonteCarloSummary` scalars + `prob_X_cheapest` returned.
- **store_results** uses total-replace semantics — running deterministic-only clears cached MC results.
- **Scenario names** are sanitized via `Path(name).name` before joining figure paths.
- **sweep_param** whitelist has 14 paths; rent paths require `spec.rent is not None`.
- **Breakdown keys** centralized as `CONDO_BREAKDOWN_KEYS`, `HOUSE_BREAKDOWN_KEYS`, `RENT_BREAKDOWN_KEYS` frozensets.

## Roadmap

Active roadmap: `docs/roadmaps/2026-06-07_housing-decision-engine.md`

Sessions:
- S1 ✅ Repo foundation (2026-06-07, PR #2)
- S2 ✅ MCP server — 6 tools, 115 tests (2026-06-08, PR #2)
- S3 ✅ 3-way comparison + income model — 151 tests (2026-06-08, PR #3)
- S4 Market scenario layer + Monte Carlo extensions

## Do not

- Add geographic tax rules (explicitly out of scope — see roadmap)
- Add mortgage optimization / leverage modeling (out of scope)
- Import from fund repos (`mm-infra`, `mm-strategies`, etc.) — this is standalone personal tooling
