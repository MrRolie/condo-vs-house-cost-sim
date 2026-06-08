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
  models.py         # Dataclasses: params + results
  pv.py             # Pure PV utility functions
  deterministic.py  # Deterministic PV engine
  monte_carlo.py    # Monte Carlo simulation engine
  config.py         # YAML config loader
  reporting.py      # Text reports + matplotlib figures
  cli.py            # CLI entry point (hde)
mcp_server/         # MCP server (S2 — not yet built)
tests/              # pytest suite
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

- **Deterministic + Monte Carlo** run as separate engines; deterministic is
  the sanity check, MC is the uncertainty surface.
- **YAML config** is the input contract — scenarios are files, not code.
- **Pure functions** throughout — no global state, seeded RNG for reproducibility.
- **MCP tools** (S2) wrap the existing engine; no engine logic in the MCP layer.

## Roadmap

Active roadmap: `docs/roadmaps/2026-06-07_housing-decision-engine.md`

Sessions:
- S1 ✅ Repo foundation (this session)
- S2 MCP server (agent-native layer)
- S3 Rent option + employment cash flow model
- S4 Market scenario layer + Monte Carlo extensions

## Do not

- Add geographic tax rules (explicitly out of scope — see roadmap)
- Add mortgage optimization / leverage modeling (out of scope)
- Import from fund repos (`mm-infra`, `mm-strategies`, etc.) — this is standalone personal tooling
