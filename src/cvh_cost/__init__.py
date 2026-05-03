"""CVH Cost - Condo vs House Cost Analysis Engine.

A Python tool for comparing the long-run present value of ownership costs
between condos and houses using deterministic and Monte Carlo analysis.

Public surface (back-compat re-exports):
    - The dataclasses, simulation engines, and reporting helpers in
      ``cvh_cost.core``.
    - YAML config loading from ``cvh_cost.config``.

The Claude-driven agent flow (questionnaire intake, market data, parameter
assembly, analysis tools) lives in ``cvh_cost.agent``.
"""

from cvh_cost.core.models import (
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
from cvh_cost.core.deterministic import compute_deterministic
from cvh_cost.core.monte_carlo import run_monte_carlo
from cvh_cost.core.pv import pv_to_monthly_savings
from cvh_cost.config import load_config

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
