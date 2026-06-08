# MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use mm-spine:subagent-driven-development (recommended) or mm-spine:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

audit-skipped: not money-path

**Goal:** Build a FastMCP server exposing 6 tools (define_scenario, run_comparison, sweep_param, save_figure, list_scenarios, delete_scenario) so Claude can run housing comparisons interactively without touching YAML files.

**Architecture:** Three-module layout — `registry.py` (in-memory scenario store), `tools.py` (6 tool implementations + serialization helpers), `main.py` (FastMCP wrappers + entry point). Engine (`src/hde/`) is imported directly; MCP layer adds zero business logic.

**Tech Stack:** FastMCP>=2.0, existing `hde` engine (deterministic + MC), matplotlib (figures already a dep), pytest.

**Spec:** `docs/specs/2026-06-07-mcp-server-design.md`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `mcp_server/__init__.py` | Empty package marker |
| Create | `mcp_server/registry.py` | `ScenarioEntry` dataclass + `_REGISTRY` dict + CRUD functions |
| Create | `mcp_server/tools.py` | 6 tool implementations + `_det_to_dict` / `_mc_to_dict` helpers |
| Create | `mcp_server/main.py` | FastMCP instance + `@mcp.tool` wrappers + `run()` entry point |
| Create | `tests/test_registry.py` | Unit tests for registry CRUD |
| Create | `tests/test_tools.py` | Integration tests for all 6 tools (calls tools.py directly, no server) |
| Create | `tests/test_mcp_smoke.py` | End-to-end chain: define → run → save_figure |
| Modify | `pyproject.toml` | Add `fastmcp>=2.0` dep; add `hde-mcp` script; add `mcp_server` to wheel packages |
| Modify | `AGENTS.md` | Update MCP server launch command |

---

## Task 1: Package scaffold + registry module

**Files:**
- Create: `mcp_server/__init__.py`
- Create: `mcp_server/registry.py`
- Create: `tests/test_registry.py`

- [ ] **Step 1: Create empty package marker**

```python
# mcp_server/__init__.py
```

- [ ] **Step 2: Write failing tests for registry**

```python
# tests/test_registry.py
import pytest
from mcp_server import registry


@pytest.fixture(autouse=True)
def clean_registry():
    registry.clear()
    yield
    registry.clear()


def test_define_and_get():
    params = (object(), object(), object(), object())
    registry.define("s1", {"years": 20}, params)
    entry = registry.get("s1")
    assert entry.name == "s1"
    assert entry.raw_config == {"years": 20}
    assert entry.params is params
    assert entry.det_result is None
    assert entry.mc_result is None


def test_define_overwrites_silently():
    registry.define("s1", {}, (1, 2, 3, 4))
    registry.define("s1", {}, (5, 6, 7, 8))
    assert registry.get("s1").params == (5, 6, 7, 8)


def test_get_missing_raises_key_error():
    with pytest.raises(KeyError):
        registry.get("nonexistent")


def test_all_entries_empty():
    assert registry.all_entries() == []


def test_all_entries_lists_names_and_result_flags():
    registry.define("a", {}, ())
    registry.define("b", {}, ())
    entries = registry.all_entries()
    assert len(entries) == 2
    assert {e["name"] for e in entries} == {"a", "b"}
    for e in entries:
        assert e["has_det_result"] is False
        assert e["has_mc_result"] is False


def test_remove_existing():
    registry.define("s1", {}, ())
    registry.remove("s1")
    with pytest.raises(KeyError):
        registry.get("s1")


def test_remove_missing_raises_key_error():
    with pytest.raises(KeyError):
        registry.remove("nonexistent")


def test_store_det_result():
    registry.define("s1", {}, ())
    sentinel = object()
    registry.store_results("s1", det_result=sentinel)
    entry = registry.get("s1")
    assert entry.det_result is sentinel
    assert entry.mc_result is None


def test_store_mc_result():
    registry.define("s1", {}, ())
    sentinel = object()
    registry.store_results("s1", mc_result=sentinel)
    entry = registry.get("s1")
    assert entry.mc_result is sentinel
    assert entry.det_result is None


def test_all_entries_reflects_result_flags():
    registry.define("s1", {}, ())
    registry.store_results("s1", det_result=object())
    entries = registry.all_entries()
    assert entries[0]["has_det_result"] is True
    assert entries[0]["has_mc_result"] is False


def test_clear_empties_registry():
    registry.define("s1", {}, ())
    registry.clear()
    assert registry.all_entries() == []
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /home/mm-mike/ai_system/projects/housing-decision-engine
uv run python -m pytest tests/test_registry.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'mcp_server'`

- [ ] **Step 4: Implement registry.py**

```python
# mcp_server/registry.py
from __future__ import annotations
from dataclasses import dataclass
from hde.models import DeterministicResult, MonteCarloResult


@dataclass
class ScenarioEntry:
    name: str
    raw_config: dict
    params: tuple  # (CondoParams, HouseParams, SimulationParams, EconomicParams)
    det_result: DeterministicResult | None = None
    mc_result: MonteCarloResult | None = None


_REGISTRY: dict[str, ScenarioEntry] = {}


def define(name: str, raw_config: dict, params: tuple) -> None:
    _REGISTRY[name] = ScenarioEntry(name=name, raw_config=raw_config, params=params)


def get(name: str) -> ScenarioEntry:
    if name not in _REGISTRY:
        raise KeyError(name)
    return _REGISTRY[name]


def all_entries() -> list[dict]:
    return [
        {
            "name": e.name,
            "has_det_result": e.det_result is not None,
            "has_mc_result": e.mc_result is not None,
        }
        for e in _REGISTRY.values()
    ]


def remove(name: str) -> None:
    if name not in _REGISTRY:
        raise KeyError(name)
    del _REGISTRY[name]


def store_results(
    name: str,
    det_result: DeterministicResult | None = None,
    mc_result: MonteCarloResult | None = None,
) -> None:
    entry = get(name)
    if det_result is not None:
        entry.det_result = det_result
    if mc_result is not None:
        entry.mc_result = mc_result


def clear() -> None:
    """Reset registry state. For tests only."""
    _REGISTRY.clear()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run python -m pytest tests/test_registry.py -v
```
Expected: 11 tests pass.

- [ ] **Step 6: Commit**

```bash
git add mcp_server/__init__.py mcp_server/registry.py tests/test_registry.py
git commit -m "feat(mcp): add ScenarioEntry registry with CRUD"
```

---

## Task 2: Serialization helpers + define_scenario

**Files:**
- Create: `mcp_server/tools.py`
- Modify: `tests/test_tools.py` (create file, add first tests)

- [ ] **Step 1: Write failing tests for serialization helpers and define_scenario**

```python
# tests/test_tools.py
import json
import pytest
import numpy as np
from hde.models import (
    DeterministicResult,
    MonteCarloResult,
    MonteCarloSummary,
)
from mcp_server import registry
from mcp_server.tools import _det_to_dict, _mc_to_dict, define_scenario


@pytest.fixture(autouse=True)
def clean_registry():
    registry.clear()
    yield
    registry.clear()


def _make_det() -> DeterministicResult:
    return DeterministicResult(
        condo_pv_base=10.0, condo_pv_events=2.0, condo_pv_other=1.0, condo_pv_total=13.0,
        house_pv_base=20.0, house_pv_events=3.0, house_pv_other=1.0, house_pv_total=24.0,
        diff_pv=11.0,
    )


def _make_mc() -> MonteCarloResult:
    arr = np.array([1.0, 2.0, 3.0])
    s = MonteCarloSummary(mean=2.0, std=1.0, p5=1.0, p50=2.0, p95=3.0)
    return MonteCarloResult(
        condo_pv=arr, house_pv=arr, diff_pv=arr,
        condo_summary=s, house_summary=s, diff_summary=s,
        prob_house_more_expensive=0.5,
    )


BASIC_CONFIG = {
    "years": 20,
    "discount_rate": 0.03,
    "condo": {"monthly_fee": 500},
    "house": {"initial_value": 400_000},
}


# --- Serialization helpers ---

def test_det_to_dict_is_json_safe():
    d = _det_to_dict(_make_det())
    json.dumps(d)  # must not raise
    assert d["diff_pv"] == 11.0
    assert d["condo_pv_total"] == 13.0


def test_mc_to_dict_no_numpy_arrays():
    d = _mc_to_dict(_make_mc())
    json.dumps(d)  # must not raise; numpy arrays would fail here
    assert d["prob_house_more_expensive"] == 0.5
    for key in ("condo", "house", "diff"):
        assert set(d[key].keys()) == {"mean", "std", "p5", "p50", "p95"}
    assert d["condo"]["mean"] == 2.0


# --- define_scenario ---

def test_define_scenario_valid():
    result = define_scenario("s1", BASIC_CONFIG)
    assert result["name"] == "s1"
    assert result["status"] == "defined"
    assert result["condo_monthly_fee"] == 500
    assert result["house_initial_value"] == 400_000
    assert result["years"] == 20


def test_define_scenario_stores_in_registry():
    define_scenario("s1", BASIC_CONFIG)
    entry = registry.get("s1")
    assert entry.name == "s1"
    assert entry.raw_config == BASIC_CONFIG


def test_define_scenario_invalid_config_returns_error():
    bad = {"years": 20, "discount_rate": 0.03, "condo": {"monthly_fee": -100}, "house": {"initial_value": 400_000}}
    result = define_scenario("bad", bad)
    # ConfigValidationError should return {"error": ...}
    assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/test_tools.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'mcp_server.tools'`

- [ ] **Step 3: Implement tools.py with helpers and define_scenario**

```python
# mcp_server/tools.py
from __future__ import annotations
import copy
import dataclasses
import time
from pathlib import Path

from hde.config import load_config_dict, ConfigValidationError
from hde.deterministic import compute_deterministic
from hde.models import DeterministicResult, MonteCarloResult
from hde.monte_carlo import run_monte_carlo
from hde.reporting import format_text_report, plot_diff_distribution, plot_pv_distributions
from mcp_server import registry

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FIGURE_CACHE_DIR: Path = Path.home() / ".cache" / "hde" / "figures"

# ---------------------------------------------------------------------------
# Serialization helpers (private — never let numpy arrays cross MCP boundary)
# ---------------------------------------------------------------------------

def _det_to_dict(det: DeterministicResult) -> dict:
    return dataclasses.asdict(det)


def _mc_to_dict(mc: MonteCarloResult) -> dict:
    def _s(summary):
        return {
            "mean": summary.mean,
            "std": summary.std,
            "p5": summary.p5,
            "p50": summary.p50,
            "p95": summary.p95,
        }
    return {
        "condo": _s(mc.condo_summary),
        "house": _s(mc.house_summary),
        "diff": _s(mc.diff_summary),
        "prob_house_more_expensive": mc.prob_house_more_expensive,
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def define_scenario(name: str, config: dict) -> dict:
    """Define a named housing scenario. Config must include 'years', 'discount_rate',
    'condo' (with 'monthly_fee'), and 'house' (with 'initial_value')."""
    try:
        params = load_config_dict(config)
    except ConfigValidationError as e:
        return {"error": f"config invalid: {e}"}
    registry.define(name, raw_config=config, params=params)
    condo, house, sim, _econ = params
    return {
        "name": name,
        "status": "defined",
        "condo_monthly_fee": condo.monthly_fee,
        "house_initial_value": house.initial_value,
        "years": sim.years,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/test_tools.py -v
```
Expected: 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/tools.py tests/test_tools.py
git commit -m "feat(mcp): add tools.py scaffold, serialization helpers, define_scenario"
```

---

## Task 3: run_comparison tool

**Files:**
- Modify: `mcp_server/tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Add failing tests for run_comparison**

Append to `tests/test_tools.py`:

```python
from mcp_server.tools import run_comparison


def test_run_comparison_both_modes():
    define_scenario("s1", BASIC_CONFIG)
    result = run_comparison("s1")
    assert result["name"] == "s1"
    assert result["mode"] == "both"
    assert isinstance(result["report"], str)
    assert len(result["report"]) > 0
    assert "deterministic" in result
    assert "monte_carlo" in result
    assert isinstance(result["deterministic"]["diff_pv"], float)
    assert 0.0 <= result["monte_carlo"]["prob_house_more_expensive"] <= 1.0


def test_run_comparison_deterministic_only():
    define_scenario("s1", BASIC_CONFIG)
    result = run_comparison("s1", mode="deterministic")
    assert "deterministic" in result
    assert "monte_carlo" not in result


def test_run_comparison_mc_only():
    define_scenario("s1", BASIC_CONFIG)
    result = run_comparison("s1", mode="monte_carlo")
    assert "monte_carlo" in result
    assert "deterministic" not in result


def test_run_comparison_stores_results_in_registry():
    define_scenario("s1", BASIC_CONFIG)
    run_comparison("s1", mode="both")
    entry = registry.get("s1")
    assert entry.det_result is not None
    assert entry.mc_result is not None


def test_run_comparison_missing_scenario():
    result = run_comparison("nonexistent")
    assert "error" in result
    assert "nonexistent" in result["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/test_tools.py::test_run_comparison_both_modes -v
```
Expected: `ImportError: cannot import name 'run_comparison'`

- [ ] **Step 3: Implement run_comparison in tools.py**

Add after `define_scenario`:

```python
def run_comparison(name: str, mode: str = "both") -> dict:
    """Run deterministic and/or Monte Carlo comparison for a named scenario.
    mode: 'deterministic' | 'monte_carlo' | 'both'."""
    try:
        entry = registry.get(name)
    except KeyError:
        return {"error": f"scenario not found: {name}"}
    condo, house, sim, econ = entry.params
    det = None
    mc = None
    if mode in ("deterministic", "both"):
        det = compute_deterministic(condo, house, sim, econ)
    if mode in ("monte_carlo", "both"):
        mc = run_monte_carlo(condo, house, sim, econ)
    registry.store_results(name, det_result=det, mc_result=mc)
    result: dict = {
        "name": name,
        "mode": mode,
        "report": format_text_report(det, mc, sim, econ),
    }
    if det is not None:
        result["deterministic"] = _det_to_dict(det)
    if mc is not None:
        result["monte_carlo"] = _mc_to_dict(mc)
    return result
```

- [ ] **Step 4: Run all tests**

```bash
uv run python -m pytest tests/test_tools.py -v
```
Expected: all tests pass (original 8 + 5 new = 13).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/tools.py tests/test_tools.py
git commit -m "feat(mcp): add run_comparison tool"
```

---

## Task 4: sweep_param tool

**Files:**
- Modify: `mcp_server/tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Add failing tests for sweep_param**

Append to `tests/test_tools.py` (add `import copy` and `from hde.config import load_config_dict` to the imports block at the top of the file):

```python
from mcp_server.tools import sweep_param


def test_sweep_param_returns_rows():
    define_scenario("s1", BASIC_CONFIG)
    result = sweep_param("s1", "condo.monthly_fee", [400.0, 500.0, 600.0])
    assert "rows" in result
    assert len(result["rows"]) == 3
    assert result["param_path"] == "condo.monthly_fee"
    # Higher fee → higher condo PV → lower diff_pv (house relatively cheaper)
    pv_totals = [r["condo_pv_total"] for r in result["rows"]]
    assert pv_totals[0] < pv_totals[1] < pv_totals[2]


def test_sweep_param_top_level_key():
    define_scenario("s1", BASIC_CONFIG)
    result = sweep_param("s1", "years", [10, 20, 30])
    assert len(result["rows"]) == 3


def test_sweep_param_invalid_path_returns_error():
    define_scenario("s1", BASIC_CONFIG)
    result = sweep_param("s1", "house.events.0.base_cost", [1000.0])
    assert "error" in result
    assert "unsupported" in result["error"]


def test_sweep_param_missing_scenario():
    result = sweep_param("nonexistent", "years", [10, 20])
    assert "error" in result
    assert "nonexistent" in result["error"]


def test_sweep_does_not_mutate_registry_config():
    define_scenario("s1", BASIC_CONFIG)
    original_fee = registry.get("s1").raw_config["condo"]["monthly_fee"]
    sweep_param("s1", "condo.monthly_fee", [999.0])
    assert registry.get("s1").raw_config["condo"]["monthly_fee"] == original_fee


def test_sweep_paths_resolve_against_live_dataclass_fields():
    """Drift guard: each _SWEEP_PATHS entry must produce a valid config that load_config_dict accepts.
    If a field in models.py is renamed, this test catches the dead key before it silently no-ops."""
    from mcp_server.tools import _SWEEP_PATHS
    base = {
        "years": 20, "discount_rate": 0.03,
        "condo": {"monthly_fee": 500, "fee_escalation_rate": 0.02, "reserve_contribution_rate": 0.01},
        "house": {"initial_value": 400_000, "value_growth_rate": 0.01, "annual_maintenance_rate": 0.015},
        "simulation": {"house_maintenance_vol": 0.3, "condo_fee_vol": 0.05},
        "economic": {"inflation_rate": 0.02},
    }
    for path, (section, field) in _SWEEP_PATHS.items():
        config = copy.deepcopy(base)
        if section is None:
            config[field] = base.get(field, 20)
        else:
            config.setdefault(section, {})[field] = base.get(section, {}).get(field, 0.01)
        # Must not raise — if a field was renamed in models.py, ConfigValidationError fires here
        try:
            load_config_dict(config)
        except ConfigValidationError as e:
            pytest.fail(f"_SWEEP_PATHS[{path!r}] → invalid config: {e}")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/test_tools.py::test_sweep_param_returns_rows -v
```
Expected: `ImportError: cannot import name 'sweep_param'`

- [ ] **Step 3: Implement sweep_param in tools.py**

Add after `run_comparison`:

```python
# Whitelist: dot-notation param_path → (yaml_section_key, yaml_field_key)
# section=None means the field is at the top level of the config dict.
_SWEEP_PATHS: dict[str, tuple[str | None, str]] = {
    "years":                              (None, "years"),
    "discount_rate":                      (None, "discount_rate"),
    "condo.monthly_fee":                  ("condo", "monthly_fee"),
    "condo.fee_escalation_rate":          ("condo", "fee_escalation_rate"),
    "condo.reserve_contribution_rate":    ("condo", "reserve_contribution_rate"),
    "house.initial_value":                ("house", "initial_value"),
    "house.value_growth_rate":            ("house", "value_growth_rate"),
    "house.annual_maintenance_rate":      ("house", "annual_maintenance_rate"),
    "simulation.house_maintenance_vol":   ("simulation", "house_maintenance_vol"),
    "simulation.condo_fee_vol":           ("simulation", "condo_fee_vol"),
    "economic.inflation_rate":            ("economic", "inflation_rate"),
}


def sweep_param(name: str, param_path: str, values: list) -> dict:
    """Sweep a scalar parameter across a list of values; runs deterministic engine per value.
    param_path uses dot-notation (e.g. 'condo.monthly_fee', 'years'). Flat scalar fields only."""
    if param_path not in _SWEEP_PATHS:
        allowed = sorted(_SWEEP_PATHS.keys())
        return {"error": f"unsupported param_path: {param_path!r}. Allowed: {allowed}"}
    try:
        entry = registry.get(name)
    except KeyError:
        return {"error": f"scenario not found: {name}"}

    section, field = _SWEEP_PATHS[param_path]
    rows = []
    for value in values:
        config = copy.deepcopy(entry.raw_config)
        if section is None:
            config[field] = value
        else:
            config.setdefault(section, {})[field] = value
        try:
            params = load_config_dict(config)
        except ConfigValidationError as e:
            return {"error": f"invalid value {value!r} for {param_path!r}: {e}"}
        condo, house, sim, econ = params
        det = compute_deterministic(condo, house, sim, econ)
        rows.append({
            "value": value,
            "condo_pv_total": det.condo_pv_total,
            "house_pv_total": det.house_pv_total,
            "diff_pv": det.diff_pv,
        })
    return {"name": name, "param_path": param_path, "rows": rows}
```

- [ ] **Step 4: Run all tests**

```bash
uv run python -m pytest tests/test_tools.py -v
```
Expected: all tests pass (13 + 5 = 18).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/tools.py tests/test_tools.py
git commit -m "feat(mcp): add sweep_param tool with flat scalar whitelist"
```

---

## Task 5: save_figure tool

**Files:**
- Modify: `mcp_server/tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Add failing tests for save_figure**

Append to `tests/test_tools.py`:

```python
import os
import mcp_server.tools as tools_module
from mcp_server.tools import save_figure


def test_save_figure_requires_mc_first(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_module, "FIGURE_CACHE_DIR", tmp_path)
    define_scenario("s1", BASIC_CONFIG)
    result = save_figure("s1", "diff_distribution")
    assert "error" in result
    assert "run_comparison" in result["error"]


def test_save_figure_diff_distribution(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_module, "FIGURE_CACHE_DIR", tmp_path)
    define_scenario("s1", BASIC_CONFIG)
    run_comparison("s1", mode="monte_carlo")
    result = save_figure("s1", "diff_distribution")
    assert "path" in result
    assert os.path.exists(result["path"])
    assert result["path"].endswith(".png")


def test_save_figure_pv_distributions(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_module, "FIGURE_CACHE_DIR", tmp_path)
    define_scenario("s1", BASIC_CONFIG)
    run_comparison("s1", mode="monte_carlo")
    result = save_figure("s1", "pv_distributions")
    assert "path" in result
    assert os.path.exists(result["path"])


def test_save_figure_unknown_type(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_module, "FIGURE_CACHE_DIR", tmp_path)
    define_scenario("s1", BASIC_CONFIG)
    run_comparison("s1", mode="monte_carlo")
    result = save_figure("s1", "unknown_type")
    assert "error" in result


def test_save_figure_missing_scenario(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_module, "FIGURE_CACHE_DIR", tmp_path)
    result = save_figure("nonexistent", "diff_distribution")
    assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/test_tools.py::test_save_figure_diff_distribution -v
```
Expected: `ImportError: cannot import name 'save_figure'`

- [ ] **Step 3: Implement save_figure in tools.py**

Add after `sweep_param`:

```python
def save_figure(name: str, figure_type: str) -> dict:
    """Save a matplotlib figure for a scenario to the figure cache dir.
    figure_type: 'diff_distribution' | 'pv_distributions'.
    Returns {'path': '<absolute_path>'}.
    Requires run_comparison to have been called with mode='monte_carlo' or 'both' first."""
    try:
        entry = registry.get(name)
    except KeyError:
        return {"error": f"scenario not found: {name}"}
    if entry.mc_result is None:
        return {"error": f"no MC results for scenario {name!r} — run run_comparison first"}
    if figure_type not in ("diff_distribution", "pv_distributions"):
        return {"error": f"unknown figure_type {figure_type!r}. Options: diff_distribution, pv_distributions"}

    FIGURE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = FIGURE_CACHE_DIR / f"{name}_{figure_type}_{ts}.png"

    if figure_type == "diff_distribution":
        fig = plot_diff_distribution(entry.mc_result)
    else:
        fig = plot_pv_distributions(entry.mc_result)

    fig.savefig(str(path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(path)}
```

- [ ] **Step 4: Run all tests**

```bash
uv run python -m pytest tests/test_tools.py -v
```
Expected: all tests pass (18 + 5 = 23).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/tools.py tests/test_tools.py
git commit -m "feat(mcp): add save_figure tool"
```

---

## Task 6: list_scenarios + delete_scenario tools

**Files:**
- Modify: `mcp_server/tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_tools.py`:

```python
from mcp_server.tools import list_scenarios, delete_scenario


def test_list_scenarios_empty():
    result = list_scenarios()
    assert result == {"scenarios": [], "count": 0}


def test_list_scenarios_with_entries():
    define_scenario("a", BASIC_CONFIG)
    define_scenario("b", BASIC_CONFIG)
    result = list_scenarios()
    assert result["count"] == 2
    names = {s["name"] for s in result["scenarios"]}
    assert names == {"a", "b"}


def test_delete_scenario_existing():
    define_scenario("s1", BASIC_CONFIG)
    result = delete_scenario("s1")
    assert result == {"deleted": "s1"}
    assert list_scenarios()["count"] == 0


def test_delete_scenario_missing():
    result = delete_scenario("nonexistent")
    assert "error" in result
    assert "nonexistent" in result["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/test_tools.py::test_list_scenarios_empty -v
```
Expected: `ImportError: cannot import name 'list_scenarios'`

- [ ] **Step 3: Implement list_scenarios and delete_scenario in tools.py**

Add after `save_figure`:

```python
def list_scenarios() -> dict:
    """List all defined scenarios with their result-cached status."""
    entries = registry.all_entries()
    return {"scenarios": entries, "count": len(entries)}


def delete_scenario(name: str) -> dict:
    """Remove a scenario from the session registry."""
    try:
        registry.remove(name)
    except KeyError:
        return {"error": f"scenario not found: {name}"}
    return {"deleted": name}
```

- [ ] **Step 4: Run all tests**

```bash
uv run python -m pytest tests/test_tools.py -v
```
Expected: all tests pass (23 + 4 = 27).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/tools.py tests/test_tools.py
git commit -m "feat(mcp): add list_scenarios and delete_scenario tools"
```

---

## Task 7: FastMCP main.py + pyproject.toml + AGENTS.md

**Files:**
- Create: `mcp_server/main.py`
- Modify: `pyproject.toml`
- Modify: `AGENTS.md`

- [ ] **Step 1: Add fastmcp dependency and update pyproject.toml**

In `pyproject.toml`, add `"fastmcp>=2.0"` to `dependencies` and update the wheel packages and scripts:

```toml
dependencies = [
    "numpy>=1.20.0",
    "pyyaml>=6.0",
    "matplotlib>=3.5.0",
    "pandas>=1.3.0",
    "fastmcp>=2.0",
]

[project.scripts]
hde = "hde.cli:main"
hde-mcp = "mcp_server.main:run"

[tool.hatch.build.targets.wheel]
packages = ["src/hde", "mcp_server"]
```

- [ ] **Step 2: Sync dependencies**

```bash
uv sync --extra dev
```
Expected: `fastmcp` installed, no errors.

- [ ] **Step 3: Implement main.py**

```python
# mcp_server/main.py
from fastmcp import FastMCP
from mcp_server.tools import (
    define_scenario,
    run_comparison,
    sweep_param,
    save_figure,
    list_scenarios,
    delete_scenario,
)

mcp = FastMCP(
    name="housing-decision-engine",
    instructions=(
        "Housing cost comparison engine. Define named scenarios with define_scenario, "
        "then run comparisons, sweep parameters, and save figures. "
        "Scenarios are session-scoped — they reset when the server restarts. "
        "Use list_scenarios to orient yourself in a long session."
    ),
)


@mcp.tool
def define_scenario_tool(name: str, config: dict) -> dict:
    """Define a named housing scenario from a config dict.

    Required config keys: 'years' (int), 'discount_rate' (float),
    'condo' dict with 'monthly_fee' (float),
    'house' dict with 'initial_value' (float).

    Optional: 'economic', 'simulation' sections — see examples/basic_config.yaml.
    """
    return define_scenario(name, config)


@mcp.tool
def run_comparison_tool(name: str, mode: str = "both") -> dict:
    """Run a housing cost comparison for a named scenario.

    mode: 'deterministic' (fast), 'monte_carlo' (full uncertainty), or 'both' (default).
    Returns text report + structured summary dict. Caches results for save_figure.
    """
    return run_comparison(name, mode)


@mcp.tool
def sweep_param_tool(name: str, param_path: str, values: list) -> dict:
    """Sweep a scalar parameter across a list of values using the deterministic engine.

    param_path uses dot-notation. Supported paths:
    years, discount_rate,
    condo.monthly_fee, condo.fee_escalation_rate, condo.reserve_contribution_rate,
    house.initial_value, house.value_growth_rate, house.annual_maintenance_rate,
    simulation.house_maintenance_vol, simulation.condo_fee_vol,
    economic.inflation_rate.

    Returns rows: [{value, condo_pv_total, house_pv_total, diff_pv}, ...].
    """
    return sweep_param(name, param_path, values)


@mcp.tool
def save_figure_tool(name: str, figure_type: str) -> dict:
    """Save a matplotlib figure to ~/.cache/hde/figures/ and return its absolute path.

    figure_type: 'diff_distribution' or 'pv_distributions'.
    Requires run_comparison_tool to have been called with mode='monte_carlo' or 'both' first.
    Use Claude Code's SendUserFile to display the returned path to the user.
    """
    return save_figure(name, figure_type)


@mcp.tool
def list_scenarios_tool() -> dict:
    """List all scenarios defined in this session with their result-cached status."""
    return list_scenarios()


@mcp.tool
def delete_scenario_tool(name: str) -> dict:
    """Remove a scenario from the session registry."""
    return delete_scenario(name)


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Update AGENTS.md — MCP server launch command**

Replace the placeholder MCP line in `AGENTS.md`:

```
# MCP server (after S2)
uv run python -m mcp_server.main   # placeholder — update when built
```

with:

```
# MCP server
uv run hde-mcp                         # stdio transport (Claude Code)
# Register with Claude Code:
# claude mcp add hde -- uv --directory /home/mm-mike/ai_system/projects/housing-decision-engine run hde-mcp
```

- [ ] **Step 5: Verify main.py imports cleanly**

```bash
uv run python -c "from mcp_server.main import mcp; print('tools:', [t for t in dir(mcp)])"
```
Expected: no import errors; output includes tool names.

- [ ] **Step 6: Commit**

```bash
git add mcp_server/main.py pyproject.toml AGENTS.md uv.lock
git commit -m "feat(mcp): add FastMCP main.py, hde-mcp entry point, fastmcp dep"
```

---

## Task 8: End-to-end smoke test + full suite

**Files:**
- Create: `tests/test_mcp_smoke.py`

- [ ] **Step 1: Write smoke test**

```python
# tests/test_mcp_smoke.py
"""End-to-end chain: define → run → sweep → save_figure."""
import os
import pytest
import mcp_server.tools as tools_module
from mcp_server import registry
from mcp_server.tools import (
    define_scenario,
    run_comparison,
    sweep_param,
    save_figure,
    list_scenarios,
    delete_scenario,
)

BASIC_CONFIG = {
    "years": 20,
    "discount_rate": 0.03,
    "condo": {"monthly_fee": 500, "fee_escalation_rate": 0.02},
    "house": {"initial_value": 400_000, "annual_maintenance_rate": 0.015},
}


@pytest.fixture(autouse=True)
def clean():
    registry.clear()
    yield
    registry.clear()


def test_full_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_module, "FIGURE_CACHE_DIR", tmp_path)

    # Define
    r1 = define_scenario("smoke", BASIC_CONFIG)
    assert r1["status"] == "defined"

    # Run both modes
    r2 = run_comparison("smoke", mode="both")
    assert "deterministic" in r2
    assert "monte_carlo" in r2
    assert isinstance(r2["report"], str) and len(r2["report"]) > 0

    # Sweep condo fee
    r3 = sweep_param("smoke", "condo.monthly_fee", [400.0, 500.0, 600.0])
    assert len(r3["rows"]) == 3
    fees = [row["condo_pv_total"] for row in r3["rows"]]
    assert fees[0] < fees[1] < fees[2]

    # Save figure
    r4 = save_figure("smoke", "diff_distribution")
    assert "path" in r4
    assert os.path.exists(r4["path"])

    # List
    r5 = list_scenarios()
    assert r5["count"] == 1
    assert r5["scenarios"][0]["has_mc_result"] is True

    # Delete
    r6 = delete_scenario("smoke")
    assert r6 == {"deleted": "smoke"}
    assert list_scenarios()["count"] == 0


def test_two_scenario_session(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_module, "FIGURE_CACHE_DIR", tmp_path)

    config_a = {**BASIC_CONFIG, "condo": {"monthly_fee": 400}}
    config_b = {**BASIC_CONFIG, "condo": {"monthly_fee": 800}}

    define_scenario("cheap_condo", config_a)
    define_scenario("expensive_condo", config_b)

    run_comparison("cheap_condo", mode="deterministic")
    run_comparison("expensive_condo", mode="deterministic")

    cheap_diff = registry.get("cheap_condo").det_result.diff_pv
    expensive_diff = registry.get("expensive_condo").det_result.diff_pv

    # Cheaper condo fee → higher diff_pv (house is relatively more expensive vs cheaper condo)
    assert cheap_diff > expensive_diff
```

- [ ] **Step 2: Run smoke tests**

```bash
uv run python -m pytest tests/test_mcp_smoke.py -v
```
Expected: 2 tests pass.

- [ ] **Step 3: Run full test suite**

```bash
uv run python -m pytest -v
```
Expected: 76 (original) + 27 (test_tools) + 11 (test_registry) + 2 (smoke) = 116 tests pass.

- [ ] **Step 4: Final commit**

```bash
git add tests/test_mcp_smoke.py
git commit -m "test(mcp): add end-to-end smoke tests"
```

---

## Self-Review Notes

**Spec coverage:**
- `define_scenario` ✓ Task 2 | `run_comparison` ✓ Task 3 | `sweep_param` ✓ Task 4 | `save_figure` ✓ Task 5 | `list_scenarios` + `delete_scenario` ✓ Task 6 | `main.py` ✓ Task 7 | `hde-mcp` entry point ✓ Task 7 | `audit-skipped: not money-path` ✓ header
- `_SWEEP_PATHS` whitelist matches spec exactly (11 paths) ✓
- `_mc_to_dict` explicit extraction (not `dataclasses.asdict`) ✓ — load-bearing per elegance audit
- `compare_scenarios` intentionally absent (cut by elegance audit) ✓
- `AGENTS.md` MCP launch command updated ✓

**Walking skeleton:** No external network APIs, stores, or serialization formats introduced. FastMCP stdio transport is validated by actuarial-system live reference. No probe task needed.

**Type consistency:** `ScenarioEntry.params` is `tuple` throughout. `_det_to_dict` → `dataclasses.asdict` → returns `dict[str, float]`. `_mc_to_dict` → explicit `dict[str, dict | float]`. Consistent across all tasks.

**Test-block consistency:** All test assertions use realistic tolerances (ordering comparisons, not float equality). No contradictory guard + test pairs. Smoke test directional assertion (`cheap_diff > expensive_diff`) is mathematically correct — lower condo fee means condo costs less relative to house, so `diff_pv = house - condo` is larger.
