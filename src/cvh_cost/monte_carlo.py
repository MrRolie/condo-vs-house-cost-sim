"""
Monte Carlo simulation for condo vs house cost analysis.

This module provides functions for running Monte Carlo simulations
with randomness in:
- Annual cost levels (via volatility parameters)
- Event timing (via jitter around expected year)
- Event costs (via cost volatility)
"""

from typing import List

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
) -> int:
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
    rng: np.random.Generator,
) -> float:
    """
    Sample the cost of an event.
    
    Applies multiplicative shock: cost = base_cost * max(0, 1 + shock)
    where shock ~ Normal(0, cost_vol)
    
    Args:
        event: Event configuration
        rng: Random number generator
    
    Returns:
        Sampled cost (non-negative)
    """
    if event.cost_vol <= 0:
        return event.base_cost
    
    shock = rng.normal(0, event.cost_vol)
    return event.base_cost * max(0.0, 1.0 + shock)


def _simulate_condo_pv_once(
    condo: CondoParams,
    sim: SimulationParams,
    rng: np.random.Generator,
) -> float:
    """
    Run one simulation of condo PV with randomness.
    
    Randomness applied to:
    - Annual fees (if condo_fee_vol > 0)
    - Event costs and timing
    """
    pv = 0.0
    base_annual_fee = condo.monthly_fee * 12
    r = sim.discount_rate
    
    # Annual fees with optional volatility
    for year in range(1, sim.years + 1):
        # Deterministic fee for this year (with escalation)
        if condo.fee_escalation_rate == 0:
            fee_t = base_annual_fee
        else:
            fee_t = base_annual_fee * (1 + condo.fee_escalation_rate) ** year
        
        # Apply random shock if volatility > 0
        if sim.condo_fee_vol > 0:
            shock = rng.normal(0, sim.condo_fee_vol)
            fee_t *= max(0.0, 1.0 + shock)
        
        pv += pv_single(fee_t, r, year)
    
    # Other recurring costs (deterministic in v1)
    for rec_cost in condo.other_recurring_costs:
        for year in range(1, sim.years + 1):
            if rec_cost.escalation_rate == 0:
                cost_t = rec_cost.annual_amount
            else:
                cost_t = rec_cost.annual_amount * (1 + rec_cost.escalation_rate) ** year
            pv += pv_single(cost_t, r, year)
    
    # Events with random timing and cost
    for event in condo.events:
        year = _sample_event_year(event, sim.years, rng)
        event_cost = _sample_event_cost(event, rng)
        pv += pv_single(event_cost, r, year)
    
    return pv


def _simulate_house_pv_once(
    house: HouseParams,
    sim: SimulationParams,
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
    
    # Annual maintenance with optional volatility
    for year in range(1, sim.years + 1):
        # House value in this year (deterministic growth)
        value_t = house.initial_value * (1 + house.value_growth_rate) ** (year - 1)
        
        # Maintenance for this year
        maint_t = house.annual_maintenance_rate * value_t
        
        # Apply random shock if volatility > 0
        if sim.house_maintenance_vol > 0:
            shock = rng.normal(0, sim.house_maintenance_vol)
            maint_t *= max(0.0, 1.0 + shock)
        
        pv += pv_single(maint_t, r, year)
    
    # Other recurring costs (deterministic in v1)
    for rec_cost in house.other_recurring_costs:
        for year in range(1, sim.years + 1):
            if rec_cost.escalation_rate == 0:
                cost_t = rec_cost.annual_amount
            else:
                cost_t = rec_cost.annual_amount * (1 + rec_cost.escalation_rate) ** year
            pv += pv_single(cost_t, r, year)
    
    # Events with random timing and cost
    for event in house.events:
        year = _sample_event_year(event, sim.years, rng)
        event_cost = _sample_event_cost(event, rng)
        pv += pv_single(event_cost, r, year)
    
    return pv


def run_monte_carlo(
    condo: CondoParams,
    house: HouseParams,
    sim: SimulationParams,
    econ: EconomicParams,  # Reserved for future use
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
        condo_pv[i] = _simulate_condo_pv_once(condo, sim, rng)
        house_pv[i] = _simulate_house_pv_once(house, sim, rng)
    
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
