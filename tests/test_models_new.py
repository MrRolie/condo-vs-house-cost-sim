"""Tests for S3 data model additions."""
import pytest
from hde.models import (
    PayDropEvent, RentParams, IncomeParams, ComparisonSpec,
    OptionResult, AffordabilityReport, ComparisonDeterministicResult,
    MonteCarloOptionResult, AffordabilityMCReport, ComparisonMonteCarloResult,
    SimulationParams, EconomicParams, CondoParams, HouseParams,
    MonteCarloSummary, CONDO_BREAKDOWN_KEYS, HOUSE_BREAKDOWN_KEYS, RENT_BREAKDOWN_KEYS,
)
import numpy as np


def _sim():
    return SimulationParams(years=10, discount_rate=0.05)


def _econ():
    return EconomicParams()


def test_pay_drop_event_defaults():
    e = PayDropEvent(year=3, magnitude=0.8)
    assert e.year == 3
    assert e.magnitude == 0.8
    assert e.year_jitter_std == 0.0
    assert e.magnitude_vol == 0.0


def test_rent_params_defaults():
    r = RentParams(monthly_rent=2000.0)
    assert r.rent_escalation_rate == 0.03
    assert r.invested_down_payment == 0.0
    assert r.investment_return_rate == 0.07
    assert r.events == []
    assert r.other_recurring_costs == []


def test_income_params_defaults():
    i = IncomeParams(annual_income=100_000.0)
    assert i.income_growth_rate == 0.03
    assert i.affordability_threshold == 0.35
    assert i.pay_drop_events == []


def test_comparison_spec_all_none_options_is_valid_at_model_level():
    # Invariant is enforced by validate_config, not __post_init__
    spec = ComparisonSpec(simulation=_sim(), economic=_econ())
    assert spec.condo is None
    assert spec.house is None
    assert spec.rent is None


def test_comparison_spec_with_options():
    condo = CondoParams(monthly_fee=800.0)
    spec = ComparisonSpec(simulation=_sim(), economic=_econ(), condo=condo)
    assert spec.condo is condo


def test_option_result_structure():
    r = OptionResult(total_pv=50_000.0, breakdown={"fee_pv": 50_000.0})
    assert r.total_pv == 50_000.0
    assert r.breakdown == {"fee_pv": 50_000.0}


def test_comparison_deterministic_result_defaults():
    r = ComparisonDeterministicResult()
    assert r.condo is None
    assert r.house is None
    assert r.rent is None
    assert r.income_report is None


def test_monte_carlo_option_result():
    pvs = np.array([1.0, 2.0, 3.0])
    summary = MonteCarloSummary(mean=2.0, std=1.0, p5=1.0, p50=2.0, p95=3.0)
    r = MonteCarloOptionResult(pvs=pvs, summary=summary)
    assert r.pvs.shape == (3,)


def test_comparison_mc_result_ranking_probs_default_none():
    r = ComparisonMonteCarloResult()
    assert r.prob_rent_cheapest is None
    assert r.prob_condo_cheapest is None
    assert r.prob_house_cheapest is None


def test_simulation_params_new_vol_fields():
    s = SimulationParams(years=10, discount_rate=0.05)
    assert s.rent_escalation_vol == 0.0
    assert s.investment_return_vol == 0.0


def test_breakdown_key_constants():
    assert "fee_pv" in CONDO_BREAKDOWN_KEYS
    assert "reserve_pv" in CONDO_BREAKDOWN_KEYS
    assert "maintenance_pv" in HOUSE_BREAKDOWN_KEYS
    assert "rent_pv" in RENT_BREAKDOWN_KEYS
    assert "invested_dp_benefit_pv" in RENT_BREAKDOWN_KEYS
