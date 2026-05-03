"""Smoke tests for the Phase-3 intake question bank and assembler."""

import pytest

from cvh_cost.agent.intake import (
    QUESTION_BANK,
    coerce_answer,
    validate_answer,
)
from cvh_cost.agent.session import AssembledParams, get_session, reset_session
from cvh_cost.agent.assemble import (
    add_event,
    add_other_recurring,
    assemble_from_session,
    intake_summary,
    set_intake,
)
from cvh_cost.core.models import (
    CondoParams,
    EconomicParams,
    HouseParams,
    SimulationParams,
)


@pytest.fixture(autouse=True)
def _fresh_session():
    reset_session()
    yield
    reset_session()


# ---------------------------------------------------------------------------
# Question bank invariants
# ---------------------------------------------------------------------------


def test_question_bank_basic():
    """QUESTION_BANK keys match the question ids and target paths resolve."""
    assert len(QUESTION_BANK) > 0

    # Build a stand-in AssembledParams so we can probe attribute paths.
    sample = AssembledParams(
        condo=CondoParams(monthly_fee=0),
        house=HouseParams(initial_value=0),
        sim=SimulationParams(years=1, discount_rate=0.0),
        econ=EconomicParams(),
        provenance={},
    )

    for qid, q in QUESTION_BANK.items():
        assert qid == q.id, f"key {qid!r} does not match question.id {q.id!r}"
        if q.target is None:
            continue
        # Walk the dotted path, asserting each level exists.
        parts = q.target.split(".")
        assert len(parts) >= 2, f"target {q.target!r} on {qid!r} must be dotted"
        head, rest = parts[0], parts[1:]
        obj = getattr(sample, head)
        for part in rest:
            assert hasattr(obj, part), (
                f"target {q.target!r} on question {qid!r} does not resolve "
                f"on AssembledParams (missing attr {part!r})"
            )
            obj = getattr(obj, part)


# ---------------------------------------------------------------------------
# Validation / coercion
# ---------------------------------------------------------------------------


def test_validate_and_coerce():
    ok, err = validate_answer("condo_monthly_hoa", "$450")
    assert ok, err
    assert coerce_answer("condo_monthly_hoa", "$450") == 450.0

    # Percent: '2.5%' -> 0.025
    assert coerce_answer("condo_hoa_growth", "2.5%") == pytest.approx(0.025)

    # Currency with commas
    assert coerce_answer("house_price", "$1,250,000") == 1_250_000.0

    # Year-typed question: year out of range fails validation.
    # horizon_years is a count, not a calendar year; use a calendar-year question.
    ok2, err2 = validate_answer("house_year_built", 1700)
    assert not ok2
    assert err2 is not None

    # Bad currency fails
    ok3, err3 = validate_answer("condo_monthly_hoa", "abc")
    assert not ok3


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def test_assemble_minimal():
    s = get_session()
    s.intake["horizon_years"] = 25
    s.intake["condo_monthly_hoa"] = 520.0
    s.intake["house_price"] = 620_000.0

    params = assemble_from_session()

    assert isinstance(params, AssembledParams)
    assert params.condo.monthly_fee == 520.0
    assert params.house.initial_value == 620_000.0
    assert params.sim.years == 25

    # Provenance entries reflect user-sourced answers.
    assert params.provenance["condo.monthly_fee"] == "user:condo_monthly_hoa"
    assert params.provenance["house.initial_value"] == "user:house_price"
    assert params.provenance["sim.years"] == "user:horizon_years"

    # And session.params is set.
    assert get_session().params is params


def test_assemble_uses_market_for_discount_rate():
    s = get_session()
    s.intake["horizon_years"] = 20
    s.intake["condo_monthly_hoa"] = 400.0
    s.intake["house_price"] = 500_000.0
    # Default discount_rate_source: leave unset (acts like use_market_rate).
    s.market["treasury_10y"] = 0.041

    params = assemble_from_session()

    assert params.sim.discount_rate == pytest.approx(0.041)
    assert params.provenance["sim.discount_rate"] == "market:treasury_10y"


def test_assemble_falls_back_to_default_discount_rate():
    s = get_session()
    s.intake["horizon_years"] = 20
    s.intake["condo_monthly_hoa"] = 400.0
    s.intake["house_price"] = 500_000.0
    # No market data, no custom rate.

    params = assemble_from_session()
    assert params.sim.discount_rate == pytest.approx(0.03)
    assert params.provenance["sim.discount_rate"] == "default"


def test_assemble_honors_custom_discount_rate():
    s = get_session()
    s.intake["horizon_years"] = 20
    s.intake["condo_monthly_hoa"] = 400.0
    s.intake["house_price"] = 500_000.0
    s.intake["discount_rate_source"] = "use_custom"
    s.intake["discount_rate_custom"] = "5%"
    # Even if a market rate is present, the user override wins.
    s.market["treasury_10y"] = 0.041

    params = assemble_from_session()
    assert params.sim.discount_rate == pytest.approx(0.05)
    assert params.provenance["sim.discount_rate"] == "user:discount_rate_custom"


# ---------------------------------------------------------------------------
# add_event / add_other_recurring / set_intake / intake_summary
# ---------------------------------------------------------------------------


def test_add_event_and_recurring_persist_through_reassembly():
    s = get_session()
    s.intake["horizon_years"] = 20
    s.intake["condo_monthly_hoa"] = 400.0
    s.intake["house_price"] = 500_000.0
    assemble_from_session()

    add_event("house", name="Roof", base_cost=15_000, expected_year=12)
    add_other_recurring("house", name="Insurance", annual_amount=1_800)

    # Re-assemble; events/recurring should carry over.
    params = assemble_from_session()
    assert len(params.house.events) == 1
    assert params.house.events[0].name == "Roof"
    assert len(params.house.other_recurring_costs) == 1
    assert params.house.other_recurring_costs[0].name == "Insurance"


def test_add_event_requires_assembled_params():
    with pytest.raises(ValueError):
        add_event("condo", name="Assess", base_cost=5_000, expected_year=5)


def test_set_intake_validates_and_coerces():
    set_intake("condo_monthly_hoa", "$450")
    s = get_session()
    assert s.intake["condo_monthly_hoa"] == 450.0

    set_intake("condo_hoa_growth", "3%")
    assert s.intake["condo_hoa_growth"] == pytest.approx(0.03)

    with pytest.raises(ValueError):
        set_intake("house_year_built", 1700)

    with pytest.raises(KeyError):
        set_intake("not_a_question", 1)


def test_intake_summary_groups_by_section_and_flags_missing():
    s = get_session()
    s.intake["horizon_years"] = 20
    s.intake["condo_monthly_hoa"] = 400.0
    summary = intake_summary()
    assert "horizon" in summary["by_section"]
    assert summary["by_section"]["horizon"]["horizon_years"] == 20
    assert "condo" in summary["by_section"]
    # house_price not yet given -> should appear in missing_required.
    assert "house_price" in summary["missing_required"]
