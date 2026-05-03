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


def _effective_growth_rate(base_rate: float, econ: EconomicParams) -> float:
    """
    Combine user growth/escalation with inflation when operating in nominal mode.
    """
    if econ.mode == "nominal":
        return (1 + base_rate) * (1 + econ.inflation_rate) - 1
    return base_rate


def _maintenance_rate_for_year(house: HouseParams, year: int) -> float:
    """
    Return maintenance rate for a given year using an optional age/condition curve.
    """
    if not house.maintenance_curve:
        return house.annual_maintenance_rate
    
    # Find surrounding points for interpolation
    points = house.maintenance_curve
    if year <= points[0][0]:
        return points[0][1]
    if year >= points[-1][0]:
        return points[-1][1]
    
    for (y0, r0), (y1, r1) in zip(points[:-1], points[1:]):
        if y0 <= year <= y1:
            span = y1 - y0
            weight = (year - y0) / span
            return r0 + weight * (r1 - r0)
    
    return house.annual_maintenance_rate


def _event_year_deterministic(event: EventConfig, years: int) -> int:
    """
    Deterministic placement of events. For hazard-based events, fall back to expected_year.
    """
    year = event.expected_year
    if event.min_year:
        year = max(event.min_year, year)
    if event.max_year is not None:
        year = min(event.max_year, year)
    return max(1, min(year, years))


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
    econ: EconomicParams,
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
    discount_rate = sim.discount_rate
    fee_growth = _effective_growth_rate(condo.fee_escalation_rate, econ)
    reserve_growth = _effective_growth_rate(condo.reserve_growth_rate, econ)
    house_value_growth = _effective_growth_rate(house.value_growth_rate, econ)
    
    # Precompute event years deterministically
    condo_event_years = {e.name: _event_year_deterministic(e, sim.years) for e in condo.events}
    house_event_years = {e.name: _event_year_deterministic(e, sim.years) for e in house.events}
    
    # Condo simulation (deterministic)
    condo_fee = condo.monthly_fee * 12
    reserve_balance = condo.reserve_initial_balance
    condo_pv_base = 0.0
    condo_pv_events = 0.0
    condo_pv_other = 0.0
    
    # House simulation (deterministic)
    house_value = house.initial_value
    house_pv_base = 0.0
    house_pv_events = 0.0
    house_pv_other = 0.0
    
    other_cost_growth_cache = {
        "condo": [_effective_growth_rate(c.escalation_rate, econ) for c in condo.other_recurring_costs],
        "house": [_effective_growth_rate(c.escalation_rate, econ) for c in house.other_recurring_costs],
    }
    
    for year in range(1, sim.years + 1):
        # Condo base fees and reserves
        condo_fee *= (1 + fee_growth)
        reserve_balance *= (1 + reserve_growth)
        reserve_contribution = condo_fee * condo.reserve_contribution_rate
        reserve_balance += reserve_contribution
        condo_pv_base += pv_single(condo_fee, discount_rate, year)
        
        # Condo other recurring costs
        for idx, rec_cost in enumerate(condo.other_recurring_costs):
            rec_growth = other_cost_growth_cache["condo"][idx]
            amount = rec_cost.annual_amount * (1 + rec_growth) ** year
            condo_pv_other += pv_single(amount, discount_rate, year)
        
        # Condo events
        for event in condo.events:
            if condo_event_years[event.name] == year:
                event_cost = event.base_cost
                covered = min(reserve_balance, event_cost)
                reserve_balance -= covered
                net_cost = event_cost - covered
                condo_pv_events += pv_single(net_cost, discount_rate, year)
        
        # House maintenance baseline using age curve
        if year > 1:
            house_value *= (1 + house_value_growth)
        maintenance_rate = _maintenance_rate_for_year(house, year)
        maint_amount = maintenance_rate * house_value
        house_pv_base += pv_single(maint_amount, discount_rate, year)
        
        # House other recurring
        for idx, rec_cost in enumerate(house.other_recurring_costs):
            rec_growth = other_cost_growth_cache["house"][idx]
            amount = rec_cost.annual_amount * (1 + rec_growth) ** year
            house_pv_other += pv_single(amount, discount_rate, year)
        
        # House events
        for event in house.events:
            if house_event_years[event.name] == year:
                house_pv_events += pv_single(event.base_cost, discount_rate, year)
    
    condo_pv_total = condo_pv_base + condo_pv_events + condo_pv_other
    house_pv_total = house_pv_base + house_pv_events + house_pv_other
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
