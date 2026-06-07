# Housing Decision Engine — CLAUDE.md

Claude-specific guidance. Operational rules are in `AGENTS.md`.

## Skill reflexes for this repo

- New feature design → `mm-spine:brainstorming` first (always)
- Multi-step implementation → `mm-spine:writing-plans` → `mm-spine:subagent-driven-development`
- Bug / unexpected behavior → `mm-spine:systematic-debugging`
- Completing a session → `mm-spine:finishing-a-development-branch`
- MCP server questions → `mm-spine:mcp-builder` (FastMCP pattern)

## What the MCP server will expose (S2 target)

Tools Claude can call to run housing comparisons without touching notebooks or configs by hand:
- `compare_housing(config_path)` — run deterministic + MC on a named scenario
- `run_scenario(params_dict)` — inline params, no file required
- `sensitivity_sweep(param, range, config_path)` — sweep one parameter
- More TBD in S2 brainstorming

## Testing

```bash
uv run python -m pytest          # all tests
uv run python -m pytest -x -q   # fail-fast
```

## money-path: no

No fund money-path code here. No adversarial-review audit tasks needed.
Do NOT `audit-skipped` — just leave it out; it's not a money-path repo.
