"""
Domain models for the condo vs house cost analysis engine.

This module defines all the dataclasses used to represent parameters,
configurations, and results throughout the simulation.
"""

from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional, Literal, Tuple

import numpy as np
import numpy.typing as npt


@dataclass
class RecurringOtherCost:
    """
    Represents a recurring cost beyond base fees/maintenance.
    
    Examples: property insurance, property taxes, landscaping service, etc.
    
    Attributes:
        name: Descriptive name for the cost
        annual_amount: Annual cost in year 1 (base year)
        escalation_rate: Deterministic annual growth rate (0.0 = no growth)
    """
    name: str
    annual_amount: float
    escalation_rate: float = 0.0
    # Optional deterministic real escalation; stochastic piece lives in SimulationParams.other_cost_vol


@dataclass
class EventConfig:
    """
    Configuration for a one-time event (e.g., roof replacement, HVAC, special assessment).
    
    Supports both deterministic (expected_year) and stochastic timing (timing_std_years)
    as well as hazard-based timing models.
    
    Attributes:
        name: Descriptive name for the event
        base_cost: Expected cost of the event
        expected_year: The "typical" year when the event occurs (deterministic baseline)
        timing_std_years: Standard deviation for timing jitter in Monte Carlo (0.0 = no jitter)
        min_year: Earliest year the event can occur (default: 1)
        max_year: Latest year the event can occur (None = analysis horizon)
        cost_vol: Volatility for cost in Monte Carlo (std dev of normal shock, 0.0 = no randomness)
        timing_model: "jitter" (default) or "hazard"
        hazard_base: Base annual hazard (probability of occurrence) starting at hazard_start_year
        hazard_growth: Additional hazard added per year after hazard_start_year
        hazard_start_year: Year when hazard-based timing begins
        cost_distribution: Distribution used for cost shocks ("lognormal" default to avoid negatives)
    """
    name: str
    base_cost: float
    expected_year: int
    timing_std_years: float = 0.0
    min_year: int = 1
    max_year: Optional[int] = None
    cost_vol: float = 0.0
    timing_model: Literal["jitter", "hazard"] = "jitter"
    hazard_base: float = 0.0  # Annual hazard at hazard_start_year
    hazard_growth: float = 0.0  # Incremental hazard per year after hazard_start_year
    hazard_start_year: int = 1
    cost_distribution: Literal["normal", "lognormal"] = "lognormal"


@dataclass
class CondoParams:
    """
    Parameters for condo ownership costs.
    
    Attributes:
        monthly_fee: Base monthly condo/HOA fee
        fee_escalation_rate: Annual growth rate for fees (0.0 = level fees)
        events: List of one-time events (e.g., special assessments)
        other_recurring_costs: Additional recurring costs beyond the monthly fee
        reserve_contribution_rate: Fraction of annual fees set aside for reserves each year
        reserve_initial_balance: Starting reserve balance
        reserve_growth_rate: Deterministic growth on reserves
    """
    monthly_fee: float
    fee_escalation_rate: float = 0.0
    events: List[EventConfig] = field(default_factory=list)
    other_recurring_costs: List[RecurringOtherCost] = field(default_factory=list)
    reserve_contribution_rate: float = 0.0  # Fraction of annual fees set aside each year
    reserve_initial_balance: float = 0.0
    reserve_growth_rate: float = 0.0  # Deterministic annual growth on reserve balance


@dataclass
class HouseParams:
    """
    Parameters for house ownership costs.
    
    Attributes:
        initial_value: House value at year 0 (used for maintenance calculation)
        value_growth_rate: Annual growth rate of house value (for maintenance calculation)
        annual_maintenance_rate: Annual maintenance as a fraction of house value
        events: List of one-time events (e.g., roof, HVAC, plumbing)
        other_recurring_costs: Additional recurring costs beyond maintenance
        maintenance_curve: Optional (year, rate) points for age/condition curve; interpolated annually
    """
    initial_value: float
    value_growth_rate: float = 0.0
    annual_maintenance_rate: float = 0.0
    events: List[EventConfig] = field(default_factory=list)
    other_recurring_costs: List[RecurringOtherCost] = field(default_factory=list)
    maintenance_curve: List[Tuple[int, float]] = field(default_factory=list)  # (year, rate) pairs sorted by year


@dataclass
class SimulationParams:
    """
    Parameters controlling the simulation.
    
    Attributes:
        years: Analysis horizon in years
        discount_rate: Discount rate for PV calculations (nominal or real per EconomicParams)
        num_sims: Number of Monte Carlo simulations
        random_seed: Seed for reproducible random number generation
        house_maintenance_vol: Volatility (std dev) for house maintenance costs
        condo_fee_vol: Volatility (std dev) for condo fee costs
        other_cost_vol: Volatility for other_recurring_costs
        corr_inflation_house: Correlation between inflation shock and house maintenance shock
        corr_inflation_condo: Correlation between inflation shock and condo fee shock
        corr_inflation_other: Correlation between inflation shock and other cost shock
        corr_inflation_event_cost: Correlation between inflation shock and event cost shock
        shock_model: "lognormal" (default) or "normal" for multiplicative shocks
    """
    years: int
    discount_rate: float
    num_sims: int = 10_000
    random_seed: int = 42
    house_maintenance_vol: float = 0.0
    condo_fee_vol: float = 0.0
    other_cost_vol: float = 0.0
    corr_inflation_house: float = 0.0
    corr_inflation_condo: float = 0.0
    corr_inflation_other: float = 0.0
    corr_inflation_event_cost: float = 0.0
    shock_model: Literal["lognormal", "normal"] = "lognormal"
    rent_escalation_vol: float = 0.0
    investment_return_vol: float = 0.0


@dataclass
class EconomicParams:
    """
    Economic assumptions for the analysis.
    
    In v1, these are primarily documentary. The user is expected to provide
    consistent parameters (i.e., if mode is "real", discount_rate should be real).
    
    Attributes:
        mode: Whether parameters are in "nominal" or "real" terms
        inflation_rate: Expected inflation rate (used if mode == "nominal")
        inflation_vol: Volatility for annual inflation shock (used for correlation)
    """
    mode: Literal["nominal", "real"] = "real"
    inflation_rate: float = 0.0
    inflation_vol: float = 0.0


# ----- S3 Input Types -----

@dataclass
class PayDropEvent:
    """A one-time income shock event."""
    year: int
    magnitude: float        # fraction of income retained (0.8 = 20% cut)
    year_jitter_std: float = 0.0
    magnitude_vol: float = 0.0


@dataclass
class RentParams:
    """Parameters for the rent option."""
    monthly_rent: float
    rent_escalation_rate: float = 0.03
    invested_down_payment: float = 0.0
    investment_return_rate: float = 0.07
    events: List["EventConfig"] = field(default_factory=list)
    other_recurring_costs: List["RecurringOtherCost"] = field(default_factory=list)


@dataclass
class IncomeParams:
    """Employment cash flow parameters for affordability modeling."""
    annual_income: float
    income_growth_rate: float = 0.03
    affordability_threshold: float = 0.35
    pay_drop_events: List[PayDropEvent] = field(default_factory=list)


@dataclass
class ComparisonSpec:
    """Single input bundle for all comparison engines. Replaces the 4-tuple."""
    simulation: "SimulationParams"
    economic: "EconomicParams"
    condo: Optional["CondoParams"] = None
    house: Optional["HouseParams"] = None
    rent: Optional[RentParams] = None
    income: Optional[IncomeParams] = None


# ----- Result Dataclasses -----

@dataclass
class DeterministicResult:
    """
    Results from deterministic present value analysis.
    
    All values are in present value terms.
    
    Attributes:
        condo_pv_base: PV of condo monthly fees
        condo_pv_events: PV of condo one-time events
        condo_pv_other: PV of condo other recurring costs
        condo_pv_total: Total PV of condo costs
        house_pv_base: PV of house annual maintenance
        house_pv_events: PV of house one-time events
        house_pv_other: PV of house other recurring costs
        house_pv_total: Total PV of house costs
        diff_pv: house_pv_total - condo_pv_total (positive = house more expensive)
    """
    condo_pv_base: float
    condo_pv_events: float
    condo_pv_other: float
    condo_pv_total: float

    house_pv_base: float
    house_pv_events: float
    house_pv_other: float
    house_pv_total: float

    diff_pv: float


@dataclass
class MonteCarloSummary:
    """
    Summary statistics for a Monte Carlo distribution.
    
    Attributes:
        mean: Mean of the distribution
        std: Standard deviation
        p5: 5th percentile
        p50: Median (50th percentile)
        p95: 95th percentile
    """
    mean: float
    std: float
    p5: float
    p50: float
    p95: float


@dataclass
class MonteCarloResult:
    """
    Results from Monte Carlo simulation.
    
    Attributes:
        condo_pv: Array of condo PV values (shape: num_sims,)
        house_pv: Array of house PV values (shape: num_sims,)
        diff_pv: Array of house - condo PV values (shape: num_sims,)
        condo_summary: Summary statistics for condo PV distribution
        house_summary: Summary statistics for house PV distribution
        diff_summary: Summary statistics for difference distribution
        prob_house_more_expensive: P(diff_pv > 0)
    """
    condo_pv: npt.NDArray[np.float64]
    house_pv: npt.NDArray[np.float64]
    diff_pv: npt.NDArray[np.float64]

    condo_summary: MonteCarloSummary
    house_summary: MonteCarloSummary
    diff_summary: MonteCarloSummary

    prob_house_more_expensive: float


# ----- S3 Result Types -----

# Breakdown key constants — drift protection when fields are renamed
CONDO_BREAKDOWN_KEYS: FrozenSet[str] = frozenset({"fee_pv", "events_pv", "other_pv", "reserve_pv"})
HOUSE_BREAKDOWN_KEYS: FrozenSet[str] = frozenset({"maintenance_pv", "events_pv", "other_pv"})
RENT_BREAKDOWN_KEYS: FrozenSet[str] = frozenset({"rent_pv", "events_pv", "other_pv", "invested_dp_benefit_pv"})


@dataclass
class OptionResult:
    """Per-option deterministic result."""
    total_pv: float
    breakdown: dict  # keys defined by {CONDO,HOUSE,RENT}_BREAKDOWN_KEYS


@dataclass
class AffordabilityReport:
    """Deterministic affordability layer."""
    annual_incomes: List[float]
    threshold: float
    rent_ratios: Optional[List[float]] = None
    condo_ratios: Optional[List[float]] = None
    house_ratios: Optional[List[float]] = None
    years_rent_exceeds: List[int] = field(default_factory=list)
    years_condo_exceeds: List[int] = field(default_factory=list)
    years_house_exceeds: List[int] = field(default_factory=list)


@dataclass
class ComparisonDeterministicResult:
    """Replaces DeterministicResult."""
    condo: Optional[OptionResult] = None
    house: Optional[OptionResult] = None
    rent: Optional[OptionResult] = None
    income_report: Optional[AffordabilityReport] = None


@dataclass
class MonteCarloOptionResult:
    """Per-option MC result. pvs array never crosses MCP boundary."""
    pvs: npt.NDArray[np.float64]
    summary: MonteCarloSummary


@dataclass
class AffordabilityMCReport:
    """MC affordability layer."""
    threshold: float
    prob_rent_exceeds: Optional[float] = None
    prob_condo_exceeds: Optional[float] = None
    prob_house_exceeds: Optional[float] = None


@dataclass
class ComparisonMonteCarloResult:
    """Replaces MonteCarloResult."""
    condo: Optional[MonteCarloOptionResult] = None
    house: Optional[MonteCarloOptionResult] = None
    rent: Optional[MonteCarloOptionResult] = None
    prob_rent_cheapest: Optional[float] = None
    prob_condo_cheapest: Optional[float] = None
    prob_house_cheapest: Optional[float] = None
    affordability_mc: Optional[AffordabilityMCReport] = None
