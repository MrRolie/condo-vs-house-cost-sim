"""
Monte Carlo simulation for condo vs house cost analysis.

This module provides functions for running Monte Carlo simulations
with randomness in:
- Annual cost levels (via volatility parameters)
- Event timing (via jitter or hazard models)
- Event costs (via cost volatility and distribution)
- Inflation-linked correlated shocks (optional)
"""

from typing import List, Optional

import numpy as np
import numpy.typing as npt

from .models import (
    CondoParams,
    HouseParams,
    SimulationParams,
    EconomicParams,
    EventConfig,
    RecurringOtherCost,
    MonteCarloResult,
    MonteCarloSummary,
)
from .pv import pv_single


def _effective_growth_rate(base_rate: float, inflation_factor: float, econ: EconomicParams) -> float:
    """
    Combine user growth/escalation with inflation factor when in nominal mode.
    """
    if econ.mode == "nominal":
        return (1 + base_rate) * inflation_factor - 1
    return base_rate


def _draw_inflation_factor(
    rng: np.random.Generator,
    econ: EconomicParams,
) -> tuple[float, float]:
    """
    Draw an annual inflation factor and return (factor, z_inflation).
    Factor multiplies cash-flow escalation; z is used for correlated shocks.
    """
    base = 1.0 + (econ.inflation_rate if econ.mode == "nominal" else 0.0)
    if econ.inflation_vol <= 0:
        return base, 0.0
    z = float(rng.normal())
    factor = float(base * np.exp(econ.inflation_vol * z - 0.5 * econ.inflation_vol ** 2))
    return factor, z


def _correlated_z(base_z: float, rho: float, rng: np.random.Generator) -> float:
    """
    Generate a correlated standard normal using base_z as common factor.
    """
    if rho == 0:
        return float(rng.normal())
    eps = float(rng.normal())
    residual = max(0.0, 1.0 - rho ** 2)
    return rho * base_z + (residual ** 0.5) * eps


def _shock_multiplier(vol: float, z: float, model: str) -> float:
    """
    Convert a standard normal draw into a multiplicative shock.
    """
    if vol <= 0:
        return 1.0
    if model == "lognormal":
        return float(np.exp(vol * z - 0.5 * vol ** 2))
    return max(0.0, 1.0 + vol * z)


def _maintenance_rate_for_year(house: HouseParams, year: int) -> float:
    """
    Return maintenance rate for a given year using an optional age/condition curve.
    """
    if not house.maintenance_curve:
        return house.annual_maintenance_rate
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


def _sample_event_year_hazard(
    event: EventConfig,
    max_year: int,
    rng: np.random.Generator,
) -> Optional[int]:
    """
    Sample event year using a simple hazard that can rise over time.
    Returns None if the event never occurs within the horizon.
    """
    hazard_start = max(1, event.hazard_start_year)
    for year in range(1, max_year + 1):
        hazard = 0.0
        if year >= hazard_start:
            hazard = event.hazard_base + event.hazard_growth * max(0, year - hazard_start)
        hazard = min(max(hazard, 0.0), 1.0)
        if hazard <= 0:
            continue
        if rng.random() < hazard:
            return year
    return None


def _summarize_array(arr: npt.NDArray[np.float64]) -> MonteCarloSummary:
    """
    Compute summary statistics for a Monte Carlo distribution.
    """
    return MonteCarloSummary(
        mean=float(np.mean(arr)),
        std=float(np.std(arr)),
        p5=float(np.percentile(arr, 5)),
        p50=float(np.percentile(arr, 50)),
        p95=float(np.percentile(arr, 95)),
    )


def _sample_event_year(
    event: EventConfig,
    max_year: int,
    rng: np.random.Generator,
) -> Optional[int]:
    """
    Sample the year when an event occurs.
    
    Uses Option 1: jitter around expected year with Normal distribution,
    clamped to valid range.
    
    Args:
        event: Event configuration
        max_year: Maximum year (analysis horizon)
        rng: Random number generator
    
    Returns:
        Sampled year in range [1, max_year]
    """
    if event.timing_model == "hazard":
        return _sample_event_year_hazard(event, max_year, rng)
    
    mu = event.expected_year
    sigma = event.timing_std_years
    min_y = max(1, event.min_year)
    max_y = event.max_year if event.max_year is not None else max_year
    max_y = min(max_y, max_year)  # Ensure we don't exceed analysis horizon
    
    if sigma <= 0:
        # No jitter, just clamp to valid range
        return int(max(min_y, min(mu, max_y)))
    
    # Draw from Normal distribution
    y_raw = rng.normal(mu, sigma)
    
    # Clamp to valid range
    y_clamped = max(min_y, min(y_raw, max_y))
    
    # Round to nearest integer
    year = int(round(y_clamped))
    
    # Final bounds check
    return max(1, min(year, max_year))


def _sample_event_cost(
    event: EventConfig,
    z_cost: float,
) -> float:
    """
    Sample the cost of an event using the chosen distribution and z draw.
    """
    if event.cost_vol <= 0:
        return event.base_cost
    
    model = "lognormal" if event.cost_distribution == "lognormal" else "normal"
    multiplier = _shock_multiplier(event.cost_vol, z_cost, model)
    return event.base_cost * multiplier


def _simulate_condo_pv_once(
    condo: CondoParams,
    sim: SimulationParams,
    econ: EconomicParams,
    rng: np.random.Generator,
) -> float:
    """
    Run one simulation of condo PV with randomness.
    
    Randomness applied to:
    - Annual fees (if condo_fee_vol > 0)
    - Event costs and timing (hazard or jitter)
    - Other recurring costs (if other_cost_vol > 0)
    """
    pv = 0.0
    r = sim.discount_rate
    
    fee_growth_base = condo.fee_escalation_rate
    reserve_growth_base = condo.reserve_growth_rate
    
    fee_amount = condo.monthly_fee * 12
    reserve_balance = condo.reserve_initial_balance
    
    other_amounts = [c.annual_amount for c in condo.other_recurring_costs]
    
    # Precompute event years
    event_years = {event.name: _sample_event_year(event, sim.years, rng) for event in condo.events}
    
    for year in range(1, sim.years + 1):
        inflation_factor, z_inf = _draw_inflation_factor(rng, econ)
        
        # Condo fee with escalation and volatility
        fee_growth = _effective_growth_rate(fee_growth_base, inflation_factor, econ)
        fee_amount *= (1 + fee_growth)
        z_fee = _correlated_z(z_inf, sim.corr_inflation_condo, rng)
        fee_amount *= _shock_multiplier(sim.condo_fee_vol, z_fee, sim.shock_model)
        pv += pv_single(fee_amount, r, year)
        
        # Reserves
        reserve_growth = _effective_growth_rate(reserve_growth_base, inflation_factor, econ)
        reserve_balance *= (1 + reserve_growth)
        reserve_contribution = fee_amount * condo.reserve_contribution_rate
        reserve_balance += reserve_contribution
        
        # Other recurring costs with volatility
        for idx, rec_cost in enumerate(condo.other_recurring_costs):
            growth = _effective_growth_rate(rec_cost.escalation_rate, inflation_factor, econ)
            other_amounts[idx] *= (1 + growth)
            z_other = _correlated_z(z_inf, sim.corr_inflation_other, rng)
            other_amounts[idx] *= _shock_multiplier(sim.other_cost_vol, z_other, sim.shock_model)
            pv += pv_single(other_amounts[idx], r, year)
        
        # Events
        for event in condo.events:
            if event_years[event.name] is None:
                continue
            if event_years[event.name] == year:
                z_event = _correlated_z(z_inf, sim.corr_inflation_event_cost, rng)
                event_cost = _sample_event_cost(event, z_event)
                covered = min(reserve_balance, event_cost)
                reserve_balance -= covered
                net_cost = event_cost - covered
                pv += pv_single(net_cost, r, year)
    
    return pv


def _simulate_house_pv_once(
    house: HouseParams,
    sim: SimulationParams,
    econ: EconomicParams,
    rng: np.random.Generator,
) -> float:
    """
    Run one simulation of house PV with randomness.
    
    Randomness applied to:
    - Annual maintenance (if house_maintenance_vol > 0)
    - Event costs and timing
    """
    pv = 0.0
    r = sim.discount_rate
    
    value_growth_base = house.value_growth_rate
    house_value = house.initial_value
    
    other_amounts = [c.annual_amount for c in house.other_recurring_costs]
    event_years = {event.name: _sample_event_year(event, sim.years, rng) for event in house.events}
    
    for year in range(1, sim.years + 1):
        inflation_factor, z_inf = _draw_inflation_factor(rng, econ)
        
        if year > 1:
            value_growth = _effective_growth_rate(value_growth_base, inflation_factor, econ)
            house_value *= (1 + value_growth)
        
        maintenance_rate = _maintenance_rate_for_year(house, year)
        maint_t = maintenance_rate * house_value
        z_house = _correlated_z(z_inf, sim.corr_inflation_house, rng)
        maint_t *= _shock_multiplier(sim.house_maintenance_vol, z_house, sim.shock_model)
        pv += pv_single(maint_t, r, year)
        
        # Other recurring costs with volatility
        for idx, rec_cost in enumerate(house.other_recurring_costs):
            growth = _effective_growth_rate(rec_cost.escalation_rate, inflation_factor, econ)
            other_amounts[idx] *= (1 + growth)
            z_other = _correlated_z(z_inf, sim.corr_inflation_other, rng)
            other_amounts[idx] *= _shock_multiplier(sim.other_cost_vol, z_other, sim.shock_model)
            pv += pv_single(other_amounts[idx], r, year)
        
        # Events
        for event in house.events:
            if event_years[event.name] is None:
                continue
            if event_years[event.name] == year:
                z_event = _correlated_z(z_inf, sim.corr_inflation_event_cost, rng)
                event_cost = _sample_event_cost(event, z_event)
                pv += pv_single(event_cost, r, year)
    
    return pv


def run_monte_carlo(
    condo: CondoParams,
    house: HouseParams,
    sim: SimulationParams,
    econ: EconomicParams,
) -> MonteCarloResult:
    """
    Run Monte Carlo simulation for condo vs house cost comparison.
    
    Simulates randomness in:
    - Condo annual fees (via sim.condo_fee_vol)
    - House annual maintenance (via sim.house_maintenance_vol)
    - Event timing (via EventConfig.timing_std_years)
    - Event costs (via EventConfig.cost_vol)
    
    Args:
        condo: Condo cost parameters
        house: House cost parameters
        sim: Simulation parameters including volatilities and num_sims
        econ: Economic parameters (reserved for future extensions)
    
    Returns:
        MonteCarloResult with arrays of simulated PVs and summary statistics
    
    Note:
        - Other recurring costs are treated deterministically in v1
        - RNG is seeded with sim.random_seed for reproducibility
        - This function has no side effects and does not print anything
    """
    rng = np.random.default_rng(sim.random_seed)
    
    # Preallocate arrays
    condo_pv = np.empty(sim.num_sims, dtype=np.float64)
    house_pv = np.empty(sim.num_sims, dtype=np.float64)
    
    # Run simulations
    for i in range(sim.num_sims):
        condo_pv[i] = _simulate_condo_pv_once(condo, sim, econ, rng)
        house_pv[i] = _simulate_house_pv_once(house, sim, econ, rng)
    
    # Compute difference
    diff_pv = house_pv - condo_pv
    
    # Compute summaries
    condo_summary = _summarize_array(condo_pv)
    house_summary = _summarize_array(house_pv)
    diff_summary = _summarize_array(diff_pv)
    
    # Probability that house is more expensive
    prob_house_more_expensive = float(np.mean(diff_pv > 0))
    
    return MonteCarloResult(
        condo_pv=condo_pv,
        house_pv=house_pv,
        diff_pv=diff_pv,
        condo_summary=condo_summary,
        house_summary=house_summary,
        diff_summary=diff_summary,
        prob_house_more_expensive=prob_house_more_expensive,
    )
