"""Smoke tests for the fixture-backed market data layer.

These exercise the public surface in ``cvh_cost.agent.market`` and verify
that each fetcher caches its result onto the shared ``AgentSession``.
"""

from __future__ import annotations

import pytest

# If the parallel agent hasn't landed session.py yet, skip cleanly.
pytest.importorskip("cvh_cost.agent.session")

from cvh_cost.agent.session import get_session, reset_session
from cvh_cost.agent.market import (
    fetch_inflation_expectations,
    fetch_mortgage_rate,
    fetch_rate_curve,
    fetch_regional_benchmarks,
    market_snapshot,
    recommend_discount_rate,
)


@pytest.fixture(autouse=True)
def _fresh_session():
    """Reset the singleton session before (and after) every test."""
    reset_session()
    yield
    reset_session()


def test_fetch_rate_curve_caches_to_session():
    out = fetch_rate_curve()
    assert isinstance(out, dict)
    assert "yields" in out
    assert "10y" in out["yields"]

    market = get_session().market
    assert market["rate_curve"] == out
    assert market["treasury_10y"] == pytest.approx(out["yields"]["10y"])


def test_fetch_inflation():
    out = fetch_inflation_expectations()
    for key in ("cpi_yoy", "core_cpi_yoy", "breakeven_5y", "breakeven_10y"):
        assert key in out, f"missing key {key}"
        assert isinstance(out[key], float)

    market = get_session().market
    assert market["inflation"] == out
    assert market["cpi_yoy"] == pytest.approx(out["cpi_yoy"])


def test_fetch_mortgage_rate():
    out = fetch_mortgage_rate(term=30)
    assert out["term"] == 30
    assert isinstance(out["rate"], float) and out["rate"] > 0
    assert get_session().market["mortgage_30y"] == out

    out15 = fetch_mortgage_rate(term=15)
    assert out15["term"] == 15
    assert get_session().market["mortgage_15y"] == out15

    with pytest.raises(ValueError):
        fetch_mortgage_rate(term=20)


def test_fetch_regional_benchmarks_match_and_default():
    boston = fetch_regional_benchmarks("Greater Boston Area")
    assert boston["matched_region"] == "boston"
    assert "house_maintenance_pct" in boston
    assert "house_insurance_annual" in boston
    assert "condo_hoa_per_sqft_month" in boston
    assert get_session().market["benchmark:boston"] == boston

    mars = fetch_regional_benchmarks("Mars Colony")
    assert mars["matched_region"] == "default"
    assert "house_maintenance_pct" in mars
    assert get_session().market["benchmark:default"] == mars


def test_recommend_discount_rate_real_vs_nominal():
    nominal = recommend_discount_rate(horizon_years=10, mode="nominal")
    real = recommend_discount_rate(horizon_years=10, mode="real")

    # Nominal should match the fixture's 10y yield closely.
    curve = get_session().market["rate_curve"]
    expected_nominal = curve["yields"]["10y"]
    assert nominal["tenor"] == "10y"
    assert nominal["mode"] == "nominal"
    assert nominal["rate"] == pytest.approx(expected_nominal)
    assert nominal["rationale"]

    # Real should be approximately nominal minus the 10y breakeven.
    inflation = get_session().market["inflation"]
    expected_real = expected_nominal - inflation["breakeven_10y"]
    assert real["tenor"] == "10y"
    assert real["mode"] == "real"
    assert real["rate"] == pytest.approx(max(0.0, expected_real))
    assert real["rationale"]
    # Sanity: a non-zero, positive real rate at horizon=10.
    assert real["rate"] > 0
    assert real["rate"] < nominal["rate"]


def test_recommend_discount_rate_short_horizon_uses_5y_breakeven():
    out = recommend_discount_rate(horizon_years=5, mode="real")
    inflation = get_session().market["inflation"]
    # 5y breakeven, not 10y, since horizon <= 7.
    assert "5y breakeven" in out["rationale"]
    expected = max(0.0, get_session().market["rate_curve"]["yields"]["5y"]
                   - inflation["breakeven_5y"])
    assert out["rate"] == pytest.approx(expected)


def test_market_snapshot_returns_copy():
    fetch_rate_curve()
    snap = market_snapshot()
    assert "rate_curve" in snap
    # Mutating the snapshot must not affect the live session state.
    snap["rate_curve"]["yields"]["10y"] = 9.99
    assert get_session().market["rate_curve"]["yields"]["10y"] != 9.99
