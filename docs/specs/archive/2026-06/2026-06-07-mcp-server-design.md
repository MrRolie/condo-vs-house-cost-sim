# MCP Server Design — Housing Decision Engine (S2)

**money-path: no**
**Date:** 2026-06-07
**Session:** S2 of `docs/roadmaps/2026-06-07_housing-decision-engine.md`

## Goal

Expose the `hde` engine as an MCP server so Claude can run housing comparisons,
define named scenarios, sweep parameters, and surface matplotlib figures —
all without touching YAML files or notebooks.

## Intent / character

Session-long exploration tool. Claude defines scenarios once by name, then runs
what-ifs against them. Stateless per restart (acceptable for personal lain-node
use). Figures saved to disk; Claude uses `SendUserFile` to show them.

## Architecture

```
mcp_server/
  __init__.py
  main.py      # FastMCP instance + @mcp.tool thin wrappers; mcp.run() entry
  registry.py  # In-memory ScenarioEntry store; module-level _REGISTRY dict
  tools.py     # Tool implementations + inline serialization helpers
```

Engine (`src/hde/`) is imported directly. MCP layer adds zero business logic —
all computation stays in the engine. `serialization.py` was audited out — the
~8-line det/MC→dict conversion is inlined in `tools.py`.

Figure cache: `~/.cache/hde/figures/` — created on first use.

## Registry data model

```python
@dataclass
class ScenarioEntry:
    name: str
    raw_config: dict                          # original config dict (for sweep cloning)
    params: tuple                             # (CondoParams, HouseParams, SimulationParams, EconomicParams)
    det_result: DeterministicResult | None = None
    mc_result: MonteCarloResult | None = None # full numpy arrays; never leaves process
```

Module-level `_REGISTRY: dict[str, ScenarioEntry]`. Process-scoped — cleared on restart.
`list_scenarios`, `delete_scenario`, `define_scenario` mutate this dict directly.

## Serialization (inlined in tools.py)

Two private helpers in `tools.py`:

- `_det_to_dict(det: DeterministicResult) -> dict` — `dataclasses.asdict(det)`; all fields are floats, JSON-safe.
- `_mc_to_dict(mc: MonteCarloResult) -> dict` — explicit field extraction: `MonteCarloSummary` scalars (mean, std, p5, p50, p95) for condo/house/diff, plus `prob_house_more_expensive`. Raw numpy arrays **never** cross the MCP boundary (`dataclasses.asdict` would crash on them — explicit extraction is load-bearing, not optional).

## Tool API (6 tools)

All tools return dicts. Known domain errors (`ConfigValidationError`, `KeyError` for
missing scenario) return `{"error": "<message>"}`. Unexpected exceptions propagate
normally — masked tracebacks are invisible to a solo operator debugging a crashed tool.
Tools are registered via `@mcp.tool` on thin wrappers in `main.py` that delegate to
`tools.py` implementations.

---

### `define_scenario(name: str, config: dict) -> dict`

Validates `config` via `load_config_dict()`. Stores a `ScenarioEntry` in `_REGISTRY`
under `name` (overwrites silently if name already exists).

**Returns:**
```json
{
  "name": "downtown_condo",
  "status": "defined",
  "condo_monthly_fee": 650,
  "house_initial_value": 750000,
  "years": 25
}
```

**Errors:** `ConfigValidationError` from engine → `{"error": "config invalid: <detail>"}`.

---

### `run_comparison(name: str, mode: str = "both") -> dict`

`mode`: `"deterministic"` | `"monte_carlo"` | `"both"`.

Looks up scenario from `_REGISTRY`. Runs engine. Stores `det_result` and/or
`mc_result` back on the `ScenarioEntry`. Returns text report + structured summary.

**Returns:**
```json
{
  "name": "downtown_condo",
  "mode": "both",
  "report": "<format_text_report() output>",
  "deterministic": {
    "condo_pv_total": 95000,
    "house_pv_total": 110000,
    "diff_pv": 15000
  },
  "monte_carlo": {
    "condo": {"mean": 95200, "std": 8100, "p5": 82000, "p50": 95000, "p95": 110000},
    "house": {"mean": 110500, "std": 12000, "p5": 91000, "p50": 110000, "p95": 133000},
    "diff":  {"mean": 15300, "std": 9800, "p5": -1200, "p50": 15000, "p95": 33000},
    "prob_house_more_expensive": 0.847
  }
}
```

**Errors:** `{"error": "scenario not found: <name>"}`.

---

### `sweep_param(name: str, param_path: str, values: list) -> dict`

Supported `param_path` patterns (dot notation, flat scalar fields only — no list indexing):
- `"condo.monthly_fee"`, `"condo.fee_escalation_rate"`, `"condo.reserve_contribution_rate"`
- `"house.initial_value"`, `"house.value_growth_rate"`, `"house.annual_maintenance_rate"`
- `"sim.years"`, `"sim.discount_rate"`, `"sim.house_maintenance_vol"`, `"sim.condo_fee_vol"`
- `"econ.inflation_rate"`

For each value: clones `raw_config`, patches the field, calls `load_config_dict` +
`compute_deterministic`. Monte Carlo excluded from sweep (deterministic is the right
engine for parameter sensitivity). Results are NOT stored back in the registry.

**Returns:**
```json
{
  "name": "downtown_condo",
  "param_path": "condo.monthly_fee",
  "rows": [
    {"value": 500, "condo_pv_total": 78000, "house_pv_total": 110000, "diff_pv": 32000},
    {"value": 650, "condo_pv_total": 95000, "house_pv_total": 110000, "diff_pv": 15000},
    {"value": 800, "condo_pv_total": 112000, "house_pv_total": 110000, "diff_pv": -2000}
  ]
}
```

**Errors:** `{"error": "unsupported param_path: <path>"}` for non-flat or unknown paths.

---

### `save_figure(name: str, figure_type: str) -> dict`

`figure_type`: `"diff_distribution"` | `"pv_distributions"`.

Requires MC results in registry (`run_comparison` with `mode="monte_carlo"` or `"both"`
must have been called first).

Saves to `~/.cache/hde/figures/<name>_<figure_type>_<unix_ts>.png`. Creates dir on
first use. Returns absolute path.

**Returns:** `{"path": "/home/mm-mike/.cache/hde/figures/downtown_condo_diff_distribution_1749290000.png"}`

**Errors:** `{"error": "no MC results for scenario <name> — run run_comparison first"}`.

---

### `list_scenarios() -> dict`

**Returns:**
```json
{
  "scenarios": [
    {"name": "downtown_condo", "has_det_result": true, "has_mc_result": true},
    {"name": "suburban_house", "has_det_result": false, "has_mc_result": false}
  ],
  "count": 2
}
```

---

### `delete_scenario(name: str) -> dict`

Removes entry from `_REGISTRY`. **Returns:** `{"deleted": "downtown_condo"}`.
**Errors:** `{"error": "scenario not found: <name>"}`.

---

## Entry point

`pyproject.toml` adds:
```toml
[project.scripts]
hde-mcp = "mcp_server.main:run"
```

`main.py` exposes a `run()` function that calls `mcp.run()` (stdio transport, matching
the actuarial-system pattern). Claude Code connects via `claude mcp add`.

## Import note

`load_config_dict` lives in `hde.config` (line 351) but is not re-exported via
`hde.__init__`. Import it directly: `from hde.config import load_config_dict`.

## Testing strategy

- **`tests/test_registry.py`** — unit tests: define/get/list/delete; overwrite; missing key.
- **`tests/test_tools.py`** — integration tests calling `tools.py` functions directly
  (no MCP server). Covers: happy path for all 6 tools; error paths (unknown name,
  missing results, invalid param_path).
- **`tests/test_mcp_smoke.py`** — one smoke test: define → run → save_figure → verify
  file exists at returned path.
- No mocking of the `hde` engine — tools.py tests use the real engine with
  `examples/basic_config.yaml` values inline.

## Assumptions

- FastMCP stdio transport (not HTTP) — Claude Code connects via `claude mcp add hde uv run hde-mcp`.
- Figure files are ephemeral — not cleaned up automatically; operator manages `~/.cache/hde/figures/`.
- Registry is single-process; no thread-safety needed (Claude Code calls tools serially).
- `compare_scenarios` auto-runs missing results rather than erroring — reduces tool-call overhead in sessions.
