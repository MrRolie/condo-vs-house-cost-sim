"""Compute core: pure simulation engines, dataclasses, and reporting helpers.

Nothing in this package may call out to LLMs, the network, or the user.
Anything that does belongs in ``cvh_cost.agent``.
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
from cvh_cost.core.pv import (
    pv_single,
    pv_annuity,
    pv_growth_annuity,
    pv_series,
    pv_recurring_with_escalation,
    pv_to_monthly_savings,
)
from cvh_cost.core.reporting import (
    format_text_report,
    plot_diff_distribution,
    plot_pv_distributions,
    plot_sensitivity,
)

__all__ = [
    "CondoParams",
    "HouseParams",
    "SimulationParams",
    "EconomicParams",
    "EventConfig",
    "RecurringOtherCost",
    "DeterministicResult",
    "MonteCarloResult",
    "MonteCarloSummary",
    "compute_deterministic",
    "run_monte_carlo",
    "pv_single",
    "pv_annuity",
    "pv_growth_annuity",
    "pv_series",
    "pv_recurring_with_escalation",
    "pv_to_monthly_savings",
    "format_text_report",
    "plot_diff_distribution",
    "plot_pv_distributions",
    "plot_sensitivity",
]
