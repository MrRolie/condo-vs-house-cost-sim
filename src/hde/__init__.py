"""
Housing Decision Engine

Present value comparison engine for rent / condo / house decisions,
with employment cash flow modeling and real estate market scenario analysis.
"""

from hde.models import (
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
from hde.deterministic import compute_deterministic
from hde.monte_carlo import run_monte_carlo
from hde.config import load_config
from hde.pv import pv_to_monthly_savings

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
