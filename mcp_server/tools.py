# mcp_server/tools.py
from __future__ import annotations
import copy
import dataclasses
import time
from pathlib import Path

from hde.config import load_config_dict, ConfigValidationError
from hde.deterministic import compute_deterministic
from hde.models import DeterministicResult, MonteCarloResult
from hde.monte_carlo import run_monte_carlo
from hde.reporting import format_text_report, plot_diff_distribution, plot_pv_distributions
from mcp_server import registry

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FIGURE_CACHE_DIR: Path = Path.home() / ".cache" / "hde" / "figures"


# ---------------------------------------------------------------------------
# Serialization helpers (private)
# ---------------------------------------------------------------------------

def _det_to_dict(det: DeterministicResult) -> dict:
    return dataclasses.asdict(det)


def _mc_to_dict(mc: MonteCarloResult) -> dict:
    def _s(summary):
        return {
            "mean": summary.mean,
            "std": summary.std,
            "p5": summary.p5,
            "p50": summary.p50,
            "p95": summary.p95,
        }
    return {
        "condo": _s(mc.condo_summary),
        "house": _s(mc.house_summary),
        "diff": _s(mc.diff_summary),
        "prob_house_more_expensive": mc.prob_house_more_expensive,
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def define_scenario(name: str, config: dict) -> dict:
    """Define a named housing scenario. Config must include 'years', 'discount_rate',
    'condo' (with 'monthly_fee'), and 'house' (with 'initial_value')."""
    try:
        params = load_config_dict(config)
    except ConfigValidationError as e:
        return {"error": f"config invalid: {e}"}
    registry.define(name, raw_config=config, params=params)
    condo, house, sim, _econ = params
    return {
        "name": name,
        "status": "defined",
        "condo_monthly_fee": condo.monthly_fee,
        "house_initial_value": house.initial_value,
        "years": sim.years,
    }


def run_comparison(name: str, mode: str = "both") -> dict:
    """Run deterministic and/or Monte Carlo comparison for a named scenario.
    mode: 'deterministic' | 'monte_carlo' | 'both'."""
    try:
        entry = registry.get(name)
    except KeyError:
        return {"error": f"scenario not found: {name}"}
    condo, house, sim, econ = entry.params
    det = None
    mc = None
    if mode in ("deterministic", "both"):
        det = compute_deterministic(condo, house, sim, econ)
    if mode in ("monte_carlo", "both"):
        mc = run_monte_carlo(condo, house, sim, econ)
    registry.store_results(name, det_result=det, mc_result=mc)
    result: dict = {
        "name": name,
        "mode": mode,
        "report": format_text_report(det, mc, sim, econ),
    }
    if det is not None:
        result["deterministic"] = _det_to_dict(det)
    if mc is not None:
        result["monte_carlo"] = _mc_to_dict(mc)
    return result
