"""
CVH Cost - Condo vs House Cost Analysis Engine

A Python tool for comparing the long-run present value of ownership costs
between condos and houses using deterministic and Monte Carlo analysis.
"""

from cvh_cost.models import (
    CondoParams,
    HouseParams,
    SimulationParams,
    EconomicParams,
    EventConfig,
    RecurringOtherCost,
    DeterministicResult,
    MonteCarloResult,
    MonteCarloSummary,
)
from cvh_cost.deterministic import compute_deterministic
from cvh_cost.monte_carlo import run_monte_carlo
from cvh_cost.config import load_config
from cvh_cost.pv import pv_to_monthly_savings

__version__ = "0.1.0"

__all__ = [
    # Models
    "CondoParams",
    "HouseParams",
    "SimulationParams",
    "EconomicParams",
    "EventConfig",
    "RecurringOtherCost",
    "DeterministicResult",
    "MonteCarloResult",
    "MonteCarloSummary",
    # Functions
    "compute_deterministic",
    "run_monte_carlo",
    "load_config",
    "pv_to_monthly_savings",
]
