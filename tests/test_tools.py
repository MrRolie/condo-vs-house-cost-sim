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
    assert "error" in result
