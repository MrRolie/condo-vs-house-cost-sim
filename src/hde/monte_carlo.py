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
    MonteCarloSummary,
    ComparisonSpec,
    ComparisonMonteCarloResult,
    MonteCarloOptionResult,
    AffordabilityMCReport,
    RentParams,
    IncomeParams,
    PayDropEvent,
)
from .pv import pv_single, pv_recurring_with_escalation


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


def _simulate_rent_pv_once(
    rent: RentParams,
    sim: SimulationParams,
    econ: EconomicParams,
    rng: np.random.Generator,
) -> float:
    """
    Run one simulation of rent PV with randomness.

    Mirrors the deterministic rent model (`_compute_rent_option`) but layers on:
    - Rent escalation shock (if sim.rent_escalation_vol > 0)
    - Event costs and timing (jitter or hazard)
    - Other recurring cost volatility (if sim.other_cost_vol > 0)
    - Investment-return shock on the invested down payment
      (if sim.investment_return_vol > 0)

    Discounting uses `sim.discount_rate` directly, matching the condo/house
    simulators and the deterministic rent model.
    """
    dr = sim.discount_rate

    # Base escalation, folding in nominal-mode inflation the same way the
    # deterministic rent model does (so zero-vol MC converges to deterministic
    # in both real and nominal modes).
    base_esc = rent.rent_escalation_rate
    if econ.mode == "nominal":
        base_esc = (1 + base_esc) * (1 + econ.inflation_rate) - 1

    # Rent escalation, optionally shocked.
    if sim.rent_escalation_vol > 0:
        z_esc = float(rng.normal())
        esc_shock = _shock_multiplier(sim.rent_escalation_vol, z_esc, sim.shock_model)
        effective_esc = base_esc * esc_shock
    else:
        effective_esc = base_esc

    annual_rent = rent.monthly_rent * 12
    rent_pv = pv_recurring_with_escalation(annual_rent, effective_esc, dr, sim.years)

    # Events (same pattern as condo/house: None-guarded, correlated z draw).
    events_pv = 0.0
    event_years = {event.name: _sample_event_year(event, sim.years, rng) for event in rent.events}
    for event in rent.events:
        year = event_years[event.name]
        if year is None:
            continue
        z_event = _correlated_z(0.0, sim.corr_inflation_event_cost, rng)
        event_cost = _sample_event_cost(event, z_event)
        events_pv += pv_single(event_cost, dr, year)

    # Other recurring costs, optionally shocked (level shock applied to the series).
    other_pv = 0.0
    for cost in rent.other_recurring_costs:
        if sim.other_cost_vol > 0:
            z_other = float(rng.normal())
            shock = _shock_multiplier(sim.other_cost_vol, z_other, sim.shock_model)
            annual = cost.annual_amount * shock
        else:
            annual = cost.annual_amount
        other_pv += pv_recurring_with_escalation(annual, cost.escalation_rate, dr, sim.years)

    # Invested down-payment benefit (reduces net cost of renting).
    if rent.invested_down_payment > 0:
        if sim.investment_return_vol > 0:
            z_inv = float(rng.normal())
            r_shock = _shock_multiplier(sim.investment_return_vol, z_inv, sim.shock_model)
            r_inv = rent.investment_return_rate * r_shock
        else:
            r_inv = rent.investment_return_rate
        benefit = rent.invested_down_payment * ((1 + r_inv) ** sim.years) / ((1 + dr) ** sim.years)
    else:
        benefit = 0.0

    return rent_pv + events_pv + other_pv - benefit


def _compute_income_affordability_once(
    income: IncomeParams,
    sim: SimulationParams,
    condo_annual_costs: List[float],
    house_annual_costs: List[float],
    rent_annual_costs: List[float],
    rng: np.random.Generator,
) -> dict:
    """
    For one MC path, draw a stochastic income trajectory and report, per option,
    whether the housing cost/income ratio exceeded the affordability threshold in
    any year.

    A single income trajectory is drawn per call and shared across all present
    options (pay-drop timing/magnitude are common to the household, not the
    housing choice).
    """
    threshold = income.affordability_threshold

    # Pre-draw jittered years for each pay-drop event (once per sim path).
    # Drawing inside the year loop would allow a single event to fire in
    # multiple years or be missed entirely within one simulation path.
    event_years: dict = {}
    for event in income.pay_drop_events:
        if event.year_jitter_std > 0:
            ev_year = max(1, min(sim.years, round(event.year + rng.normal(0, event.year_jitter_std))))
        else:
            ev_year = event.year
        event_years[id(event)] = ev_year

    # One stochastic income trajectory, shared across options.
    traj: List[float] = []
    inc = income.annual_income
    for t in range(sim.years):
        year = t + 1
        for event in income.pay_drop_events:
            if event_years[id(event)] == year:
                if event.magnitude_vol > 0:
                    mag = event.magnitude * float(np.exp(rng.normal(0, event.magnitude_vol)))
                    mag = min(max(mag, 0.01), 1.0)
                else:
                    mag = event.magnitude
                inc *= mag
        traj.append(inc)
        if t < sim.years - 1:
            inc *= (1 + income.income_growth_rate)

    result = {}
    for option_type, costs in [
        ("condo", condo_annual_costs),
        ("house", house_annual_costs),
        ("rent", rent_annual_costs),
    ]:
        if not costs:
            continue
        exceeds = any(c / i > threshold for c, i in zip(costs, traj) if i > 0)
        result[option_type] = exceeds

    return result


def run_monte_carlo(spec: ComparisonSpec) -> ComparisonMonteCarloResult:
    """
    Run Monte Carlo simulation for all options present in the spec.

    Simulates each present option (condo / house / rent) over `num_sims` paths,
    deriving per-option PV distributions, pairwise ranking probabilities
    (which option is cheapest), and — if income params are present — the
    probability that each option's cost/income ratio breaches the affordability
    threshold in any year.

    Args:
        spec: ComparisonSpec bundling simulation/economic params and the
            present option parameters (condo/house/rent/income).

    Returns:
        ComparisonMonteCarloResult with per-option results, ranking
        probabilities, and an optional affordability MC report.

    Note:
        - Only options present in the spec are simulated.
        - RNG is seeded with sim.random_seed for reproducibility.
        - Per-iteration draw order is condo -> house -> rent -> income, so
          existing condo+house numerics are preserved when rent/income absent.
        - This function has no side effects and does not print anything.
    """
    sim = spec.simulation
    econ = spec.economic
    rng = np.random.default_rng(sim.random_seed)

    n = sim.num_sims
    condo_pvs = np.empty(n, dtype=np.float64) if spec.condo is not None else None
    house_pvs = np.empty(n, dtype=np.float64) if spec.house is not None else None
    rent_pvs = np.empty(n, dtype=np.float64) if spec.rent is not None else None

    # Pre-compute deterministic annual costs for affordability (done once, not per-sim).
    afford_condo_costs: List[float] = []
    afford_house_costs: List[float] = []
    afford_rent_costs: List[float] = []
    if spec.income is not None:
        from .deterministic import _annual_costs_for_option
        if spec.condo is not None:
            afford_condo_costs = _annual_costs_for_option("condo", spec.condo, sim, econ)
        if spec.house is not None:
            afford_house_costs = _annual_costs_for_option("house", spec.house, sim, econ)
        if spec.rent is not None:
            afford_rent_costs = _annual_costs_for_option("rent", spec.rent, sim, econ)

    afford_condo_flags = (
        np.zeros(n, dtype=bool) if spec.condo is not None and spec.income is not None else None
    )
    afford_house_flags = (
        np.zeros(n, dtype=bool) if spec.house is not None and spec.income is not None else None
    )
    afford_rent_flags = (
        np.zeros(n, dtype=bool) if spec.rent is not None and spec.income is not None else None
    )

    for i in range(n):
        if spec.condo is not None:
            condo_pvs[i] = _simulate_condo_pv_once(spec.condo, sim, econ, rng)
        if spec.house is not None:
            house_pvs[i] = _simulate_house_pv_once(spec.house, sim, econ, rng)
        if spec.rent is not None:
            rent_pvs[i] = _simulate_rent_pv_once(spec.rent, sim, econ, rng)
        if spec.income is not None:
            flags = _compute_income_affordability_once(
                spec.income, sim,
                afford_condo_costs, afford_house_costs, afford_rent_costs,
                rng,
            )
            if afford_condo_flags is not None:
                afford_condo_flags[i] = flags.get("condo", False)
            if afford_house_flags is not None:
                afford_house_flags[i] = flags.get("house", False)
            if afford_rent_flags is not None:
                afford_rent_flags[i] = flags.get("rent", False)

    def _make_opt(pvs):
        if pvs is None:
            return None
        return MonteCarloOptionResult(pvs=pvs, summary=_summarize_array(pvs))

    condo_result = _make_opt(condo_pvs)
    house_result = _make_opt(house_pvs)
    rent_result = _make_opt(rent_pvs)

    # Ranking probabilities — require the arrays, so computed here (not recoverable
    # from scalar summaries). Only meaningful with >= 2 present options.
    present = [
        (name, pvs)
        for name, pvs in [("condo", condo_pvs), ("house", house_pvs), ("rent", rent_pvs)]
        if pvs is not None
    ]
    prob_condo = prob_house = prob_rent = None
    if len(present) >= 2:
        stacked = np.stack([pvs for _, pvs in present], axis=0)  # (n_options, n_sims)
        winners = np.argmin(stacked, axis=0)  # index of cheapest option per sim
        idx = {name: k for k, (name, _) in enumerate(present)}
        if "condo" in idx:
            prob_condo = float(np.mean(winners == idx["condo"]))
        if "house" in idx:
            prob_house = float(np.mean(winners == idx["house"]))
        if "rent" in idx:
            prob_rent = float(np.mean(winners == idx["rent"]))

    affordability_mc = None
    if spec.income is not None:
        affordability_mc = AffordabilityMCReport(
            threshold=spec.income.affordability_threshold,
            prob_condo_exceeds=(
                float(np.mean(afford_condo_flags)) if afford_condo_flags is not None else None
            ),
            prob_house_exceeds=(
                float(np.mean(afford_house_flags)) if afford_house_flags is not None else None
            ),
            prob_rent_exceeds=(
                float(np.mean(afford_rent_flags)) if afford_rent_flags is not None else None
            ),
        )

    return ComparisonMonteCarloResult(
        condo=condo_result,
        house=house_result,
        rent=rent_result,
        prob_condo_cheapest=prob_condo,
        prob_house_cheapest=prob_house,
        prob_rent_cheapest=prob_rent,
        affordability_mc=affordability_mc,
    )
