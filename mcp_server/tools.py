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


# Whitelist: dot-notation param_path → (yaml_section_key, yaml_field_key)
# section=None means the field is at the top level of the config dict.
_SWEEP_PATHS: dict[str, tuple[str | None, str]] = {
    "years":                              (None, "years"),
    "discount_rate":                      (None, "discount_rate"),
    "condo.monthly_fee":                  ("condo", "monthly_fee"),
    "condo.fee_escalation_rate":          ("condo", "fee_escalation_rate"),
    "condo.reserve_contribution_rate":    ("condo", "reserve_contribution_rate"),
    "house.initial_value":                ("house", "initial_value"),
    "house.value_growth_rate":            ("house", "value_growth_rate"),
    "house.annual_maintenance_rate":      ("house", "annual_maintenance_rate"),
    "simulation.house_maintenance_vol":   ("simulation", "house_maintenance_vol"),
    "simulation.condo_fee_vol":           ("simulation", "condo_fee_vol"),
    "economic.inflation_rate":            ("economic", "inflation_rate"),
}


def sweep_param(name: str, param_path: str, values: list) -> dict:
    """Sweep a scalar parameter across a list of values using the deterministic engine.
    param_path uses dot-notation (e.g. 'condo.monthly_fee', 'years'). Flat scalar fields only."""
    if param_path not in _SWEEP_PATHS:
        allowed = sorted(_SWEEP_PATHS.keys())
        return {"error": f"unsupported param_path: {param_path!r}. Allowed: {allowed}"}
    try:
        entry = registry.get(name)
    except KeyError:
        return {"error": f"scenario not found: {name}"}

    section, field = _SWEEP_PATHS[param_path]
    rows = []
    for value in values:
        config = copy.deepcopy(entry.raw_config)
        if section is None:
            config[field] = value
        else:
            config.setdefault(section, {})[field] = value
        try:
            params = load_config_dict(config)
        except ConfigValidationError as e:
            return {"error": f"invalid value {value!r} for {param_path!r}: {e}"}
        condo, house, sim, econ = params
        det = compute_deterministic(condo, house, sim, econ)
        rows.append({
            "value": value,
            "condo_pv_total": det.condo_pv_total,
            "house_pv_total": det.house_pv_total,
            "diff_pv": det.diff_pv,
        })
    return {"name": name, "param_path": param_path, "rows": rows}


def save_figure(name: str, figure_type: str) -> dict:
    """Save a matplotlib figure for a scenario to the figure cache dir.
    figure_type: 'diff_distribution' | 'pv_distributions'.
    Returns {'path': '<absolute_path>'}.
    Requires run_comparison to have been called with mode='monte_carlo' or 'both' first."""
    try:
        entry = registry.get(name)
    except KeyError:
        return {"error": f"scenario not found: {name}"}
    if entry.mc_result is None:
        return {"error": f"no MC results for scenario {name!r} — run run_comparison first"}
    if figure_type not in ("diff_distribution", "pv_distributions"):
        return {"error": f"unknown figure_type {figure_type!r}. Options: diff_distribution, pv_distributions"}

    FIGURE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = FIGURE_CACHE_DIR / f"{name}_{figure_type}_{ts}.png"

    if figure_type == "diff_distribution":
        fig = plot_diff_distribution(entry.mc_result)
    else:
        fig = plot_pv_distributions(entry.mc_result)

    fig.savefig(str(path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(path)}
