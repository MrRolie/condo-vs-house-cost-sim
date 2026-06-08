# mcp_server/tools.py
from __future__ import annotations
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from hde.config import load_config_dict, ConfigValidationError
from hde.deterministic import compute_deterministic
from hde.monte_carlo import run_monte_carlo
from hde.models import (
    ComparisonSpec,
    ComparisonDeterministicResult,
    ComparisonMonteCarloResult,
    MonteCarloSummary,
    CONDO_BREAKDOWN_KEYS,
    HOUSE_BREAKDOWN_KEYS,
    RENT_BREAKDOWN_KEYS,
)
from hde.reporting import format_text_report, plot_diff_distribution, plot_pv_distributions
from mcp_server import registry

FIGURE_CACHE_DIR: Path = Path.home() / ".cache" / "hde" / "figures"


# ---------------------------------------------------------------------------
# Serialization helpers (private)
# ---------------------------------------------------------------------------

def _det_to_dict(det: ComparisonDeterministicResult) -> dict:
    def _opt(r):
        if r is None:
            return None
        return {"total_pv": r.total_pv, "breakdown": r.breakdown}

    result = {
        "condo": _opt(det.condo),
        "house": _opt(det.house),
        "rent": _opt(det.rent),
    }
    if det.income_report is not None:
        rpt = det.income_report

        def _opt_afford(ratios, exceeds):
            if ratios is None:
                return None
            return {"ratios": ratios, "years_exceeding": exceeds}

        result["affordability"] = {
            "annual_incomes": rpt.annual_incomes,
            "threshold": rpt.threshold,
            "rent": _opt_afford(rpt.rent_ratios, rpt.years_rent_exceeds),
            "condo": _opt_afford(rpt.condo_ratios, rpt.years_condo_exceeds),
            "house": _opt_afford(rpt.house_ratios, rpt.years_house_exceeds),
        }
    else:
        result["affordability"] = None
    return result


def _mc_to_dict(mc: ComparisonMonteCarloResult) -> dict:
    def _s(s: MonteCarloSummary) -> dict:
        return {"mean": s.mean, "std": s.std, "p5": s.p5, "p50": s.p50, "p95": s.p95}

    def _opt(r):
        if r is None:
            return None
        return _s(r.summary)  # pvs arrays NEVER cross MCP boundary

    result = {
        "condo": _opt(mc.condo),
        "house": _opt(mc.house),
        "rent": _opt(mc.rent),
        "prob_condo_cheapest": mc.prob_condo_cheapest,
        "prob_house_cheapest": mc.prob_house_cheapest,
        "prob_rent_cheapest": mc.prob_rent_cheapest,
    }
    if mc.affordability_mc is not None:
        result["affordability_mc"] = {
            "threshold": mc.affordability_mc.threshold,
            "prob_condo_exceeds": mc.affordability_mc.prob_condo_exceeds,
            "prob_house_exceeds": mc.affordability_mc.prob_house_exceeds,
            "prob_rent_exceeds": mc.affordability_mc.prob_rent_exceeds,
        }
    else:
        result["affordability_mc"] = None
    return result


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def define_scenario(name: str, config: dict) -> dict:
    """Define a named housing scenario. Config must include 'years', 'discount_rate',
    and at least one of 'condo', 'house', 'rent'. Optional 'income' for affordability."""
    safe_name = Path(name).name
    try:
        spec = load_config_dict(config)
    except (ConfigValidationError, ValueError, TypeError) as e:
        return {"error": str(e)}

    overwriting = safe_name in registry._REGISTRY
    registry.define(safe_name, config, spec)
    registry.store_results(safe_name)  # total-replace: clear any stale results

    response = {
        "name": safe_name,
        "status": "defined",
        "years": spec.simulation.years,
        "discount_rate": spec.simulation.discount_rate,
    }
    # None-safe option summaries
    if spec.condo is not None:
        response["condo_monthly_fee"] = spec.condo.monthly_fee
    if spec.house is not None:
        response["house_initial_value"] = spec.house.initial_value
    if spec.rent is not None:
        response["rent_monthly_rent"] = spec.rent.monthly_rent
    if spec.income is not None:
        response["income_annual"] = spec.income.annual_income
    if overwriting:
        response["previous_results_cleared"] = True
    return response


def run_comparison(scenario_name: str, mode: str = "both") -> dict:
    """Run deterministic and/or Monte Carlo comparison for a named scenario.
    mode: 'deterministic' | 'monte_carlo' | 'both'."""
    safe_name = Path(scenario_name).name
    if safe_name not in registry._REGISTRY:
        return {"error": f"scenario '{safe_name}' not found"}
    if mode not in {"deterministic", "monte_carlo", "both"}:
        return {"error": f"unsupported mode '{mode}'; use deterministic, monte_carlo, or both"}

    entry = registry.get(safe_name)
    det_result = None
    mc_result = None

    if mode in {"deterministic", "both"}:
        det_result = compute_deterministic(entry.spec)
    if mode in {"monte_carlo", "both"}:
        mc_result = run_monte_carlo(entry.spec)

    registry.store_results(safe_name, det_result=det_result, mc_result=mc_result)

    report = format_text_report(
        det_result if det_result is not None else ComparisonDeterministicResult(),
        mc_result,
        entry.spec.simulation,
        entry.spec.economic,
    )

    response = {"name": safe_name, "mode": mode, "report": report}
    if det_result is not None:
        response["deterministic"] = _det_to_dict(det_result)
    if mc_result is not None:
        response["monte_carlo"] = _mc_to_dict(mc_result)
    return response


# Whitelist: dot-notation param_path → (spec_section_attr, dataclass_field)
# section=None means the field lives on SimulationParams (top-level config keys).
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
    "rent.monthly_rent":                  ("rent", "monthly_rent"),
    "rent.invested_down_payment":         ("rent", "invested_down_payment"),
    "rent.investment_return_rate":        ("rent", "investment_return_rate"),
}


def sweep_param(scenario_name: str, param_path: str, values: list[float]) -> dict:
    """Sweep a scalar parameter across a list of values using the deterministic engine.
    param_path uses dot-notation (e.g. 'condo.monthly_fee', 'years'). Flat scalar fields only."""
    import copy
    import dataclasses as dc

    safe_name = Path(scenario_name).name
    if safe_name not in registry._REGISTRY:
        return {"error": f"scenario '{safe_name}' not found"}
    if not values:
        return {"error": "values list is empty"}
    if param_path not in _SWEEP_PATHS:
        return {"error": f"unsupported param_path '{param_path}'. Supported: {sorted(_SWEEP_PATHS.keys())}"}

    entry = registry.get(safe_name)
    section, field = _SWEEP_PATHS[param_path]

    # Guard: option-section sweeps require that section to exist on the spec.
    if section in {"condo", "house", "rent"} and getattr(entry.spec, section) is None:
        return {"error": f"scenario '{safe_name}' has no {section} section; cannot sweep {param_path}"}

    # Coerce integer fields — JSON delivers all numbers as float (e.g. 10.0),
    # but SimulationParams.years: int — range(1, sim.years + 1) crashes on float.
    INT_FIELDS = {"years", "num_sims", "random_seed"}
    if field in INT_FIELDS:
        values = [int(v) for v in values]

    rows = []
    for v in values:
        spec_copy = copy.deepcopy(entry.spec)
        if section is None:
            # top-level SimulationParams field
            spec_copy = dc.replace(spec_copy, simulation=dc.replace(spec_copy.simulation, **{field: v}))
        else:
            section_obj = getattr(spec_copy, section)
            new_section = dc.replace(section_obj, **{field: v})
            spec_copy = dc.replace(spec_copy, **{section: new_section})
        try:
            det = compute_deterministic(spec_copy)
            row = {"value": v}
            if det.condo is not None:
                row["condo_total_pv"] = det.condo.total_pv
            if det.house is not None:
                row["house_total_pv"] = det.house.total_pv
            if det.rent is not None:
                row["rent_total_pv"] = det.rent.total_pv
            rows.append(row)
        except Exception as e:
            rows.append({"value": v, "error": str(e)})

    return {"name": safe_name, "param_path": param_path, "rows": rows}


def save_figure(scenario_name: str, figure_type: str) -> dict:
    """Save a matplotlib figure for a scenario to the figure cache dir.
    figure_type: 'diff_distribution' | 'pv_distributions'.
    Returns {'path': '<absolute_path>'}.
    Requires run_comparison to have been called with mode='monte_carlo' or 'both' first."""
    safe_name = Path(scenario_name).name
    if safe_name not in registry._REGISTRY:
        return {"error": f"scenario '{safe_name}' not found"}

    entry = registry.get(safe_name)
    if entry.mc_result is None:
        return {"error": "run run_comparison with mode='monte_carlo' or 'both' first"}

    mc = entry.mc_result
    if figure_type == "diff_distribution":
        if mc.condo is None or mc.house is None:
            return {"error": "diff_distribution requires both condo and house options"}
        diff_pvs = mc.house.pvs - mc.condo.pvs
        fig = plot_diff_distribution(diff_pvs)
    elif figure_type == "pv_distributions":
        option_arrays = {}
        if mc.condo is not None:
            option_arrays["Condo"] = mc.condo.pvs
        if mc.house is not None:
            option_arrays["House"] = mc.house.pvs
        if mc.rent is not None:
            option_arrays["Rent"] = mc.rent.pvs
        if not option_arrays:
            return {"error": "no option arrays available for pv_distributions"}
        fig = plot_pv_distributions(option_arrays)
    else:
        return {"error": f"unknown figure_type '{figure_type}'. Use diff_distribution or pv_distributions"}

    FIGURE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time_ns())
    path = FIGURE_CACHE_DIR / f"{safe_name}_{figure_type}_{ts}.png"
    fig.savefig(str(path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(path)}


def list_scenarios() -> dict:
    """List all scenarios defined in this session with their result-cached status."""
    entries = registry.all_entries()
    return {"scenarios": entries, "count": len(entries)}


def delete_scenario(name: str) -> dict:
    """Remove a scenario from the session registry."""
    try:
        registry.remove(name)
    except KeyError:
        return {"error": f"scenario not found: {name}"}
    return {"deleted": name}
