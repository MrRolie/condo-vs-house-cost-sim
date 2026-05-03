"""Agent layer: tools that Claude Code drives during an interactive session.

This package wraps the pure compute layer in ``cvh_cost.core`` with:

- ``session``: shared in-process state (intake answers, market cache, result handles).
- ``intake``: the canonical question bank used by the questionnaire skill.
- ``assemble``: maps intake answers + market data into the core dataclasses.
- ``market``: fixture-backed market data fetchers (rate curve, inflation, benchmarks).
- ``analysis``: JSON-friendly wrappers around compute_deterministic / run_monte_carlo.

Nothing in this package is required by ``cvh_cost.core``; the dependency
points one way (agent -> core).
"""
