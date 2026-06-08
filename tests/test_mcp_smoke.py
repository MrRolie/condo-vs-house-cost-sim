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
