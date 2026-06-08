# tests/test_tools.py
import copy
import json
import os
import pytest
import numpy as np
from hde.config import load_config_dict
from hde.models import (
    DeterministicResult,
    MonteCarloResult,
    MonteCarloSummary,
)
from mcp_server import registry
import mcp_server.tools as tools_module
from mcp_server.tools import _det_to_dict, _mc_to_dict, define_scenario, run_comparison, sweep_param, save_figure
from mcp_server.tools import list_scenarios, delete_scenario


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
    assert "error" in result


# --- run_comparison ---

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


# --- sweep_param ---

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
    """Drift guard: each _SWEEP_PATHS entry must produce a valid config that load_config_dict accepts."""
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
        try:
            load_config_dict(config)
        except Exception as e:
            pytest.fail(f"_SWEEP_PATHS[{path!r}] → invalid config: {e}")


# --- save_figure ---

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


# --- list_scenarios + delete_scenario ---

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


# --- cross-mode re-run stale state clearing ---

def test_run_comparison_deterministic_clears_stale_mc():
    define_scenario("s1", BASIC_CONFIG)
    run_comparison("s1", mode="both")
    assert registry.get("s1").mc_result is not None
    run_comparison("s1", mode="deterministic")
    assert registry.get("s1").mc_result is None
    assert registry.get("s1").det_result is not None
