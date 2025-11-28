"""
Deterministic present value calculations for condo vs house costs.

This module provides functions for computing the present value of
ownership costs using deterministic (fixed) parameters, without
any randomness or Monte Carlo simulation.
"""

from .models import (
    CondoParams,
    HouseParams,
    SimulationParams,
    EconomicParams,
    DeterministicResult,
    EventConfig,
    RecurringOtherCost,
)
from .pv import pv_single, pv_annuity, pv_growth_annuity, pv_recurring_with_escalation


def _compute_condo_base_pv(
    condo: CondoParams,
    sim: SimulationParams,
) -> float:
    """
    Compute PV of condo monthly fees over the analysis horizon.
    
    If fee_escalation_rate is 0, treats as level annuity.
    Otherwise, uses growing annuity formula.
    """
    annual_fee = condo.monthly_fee * 12
    
    if condo.fee_escalation_rate == 0:
        return pv_annuity(annual_fee, sim.discount_rate, sim.years)
    else:
        # First year payment includes escalation
        first_year_fee = annual_fee * (1 + condo.fee_escalation_rate)
        return pv_growth_annuity(
            first_year_fee, 
            sim.discount_rate, 
            condo.fee_escalation_rate, 
            sim.years
        )


def _compute_events_pv(
    events: list[EventConfig],
    discount_rate: float,
    years: int,
) -> float:
    """
    Compute PV of one-time events using their expected_year (deterministic).
    
    Events with expected_year outside [1, years] are clamped to valid range.
    """
    total_pv = 0.0
    for event in events:
        # Clamp year to valid range
        year = max(1, min(event.expected_year, years))
        total_pv += pv_single(event.base_cost, discount_rate, year)
    return total_pv


def _compute_other_recurring_pv(
    other_costs: list[RecurringOtherCost],
    discount_rate: float,
    years: int,
) -> float:
    """
    Compute PV of other recurring costs.
    """
    total_pv = 0.0
    for cost in other_costs:
        total_pv += pv_recurring_with_escalation(
            cost.annual_amount,
            cost.escalation_rate,
            discount_rate,
            years
        )
    return total_pv


def _compute_house_base_pv(
    house: HouseParams,
    sim: SimulationParams,
) -> float:
    """
    Compute PV of house annual maintenance over the analysis horizon.
    
    Maintenance in year t = annual_maintenance_rate * value_t
    where value_t = initial_value * (1 + value_growth_rate)^(t-1)
    
    This is a growing annuity if value_growth_rate > 0.
    """
    # Base annual maintenance at year 0 value
    base_maintenance = house.annual_maintenance_rate * house.initial_value
    
    if house.value_growth_rate == 0:
        return pv_annuity(base_maintenance, sim.discount_rate, sim.years)
    else:
        # Year 1 maintenance = base_maintenance * (1 + value_growth_rate)^0 = base_maintenance
        # Year 2 maintenance = base_maintenance * (1 + value_growth_rate)^1
        # ...
        # Year t maintenance = base_maintenance * (1 + value_growth_rate)^(t-1)
        # 
        # This is equivalent to a growing annuity where the first payment is base_maintenance
        # and growth rate is value_growth_rate
        return pv_growth_annuity(
            base_maintenance,
            sim.discount_rate,
            house.value_growth_rate,
            sim.years
        )


def compute_deterministic(
    condo: CondoParams,
    house: HouseParams,
    sim: SimulationParams,
    econ: EconomicParams,  # Reserved for future use
) -> DeterministicResult:
    """
    Compute deterministic present values for condo and house ownership costs.
    
    This function calculates PV using fixed (non-random) parameters:
    - Condo: monthly fees (with optional escalation), events, other recurring
    - House: maintenance (based on house value), events, other recurring
    
    Args:
        condo: Condo cost parameters
        house: House cost parameters
        sim: Simulation parameters (years, discount_rate)
        econ: Economic parameters (reserved for future extensions)
    
    Returns:
        DeterministicResult with PV breakdowns for condo and house
    
    Note:
        This function has no side effects and does not print anything.
        Use reporting.format_text_report() to generate human-readable output.
    """
    # Condo PV components
    condo_pv_base = _compute_condo_base_pv(condo, sim)
    condo_pv_events = _compute_events_pv(condo.events, sim.discount_rate, sim.years)
    condo_pv_other = _compute_other_recurring_pv(
        condo.other_recurring_costs, sim.discount_rate, sim.years
    )
    condo_pv_total = condo_pv_base + condo_pv_events + condo_pv_other
    
    # House PV components
    house_pv_base = _compute_house_base_pv(house, sim)
    house_pv_events = _compute_events_pv(house.events, sim.discount_rate, sim.years)
    house_pv_other = _compute_other_recurring_pv(
        house.other_recurring_costs, sim.discount_rate, sim.years
    )
    house_pv_total = house_pv_base + house_pv_events + house_pv_other
    
    # Difference (positive = house more expensive)
    diff_pv = house_pv_total - condo_pv_total
    
    return DeterministicResult(
        condo_pv_base=condo_pv_base,
        condo_pv_events=condo_pv_events,
        condo_pv_other=condo_pv_other,
        condo_pv_total=condo_pv_total,
        house_pv_base=house_pv_base,
        house_pv_events=house_pv_events,
        house_pv_other=house_pv_other,
        house_pv_total=house_pv_total,
        diff_pv=diff_pv,
    )
