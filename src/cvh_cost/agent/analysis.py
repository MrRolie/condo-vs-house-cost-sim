"""JSON-friendly wrappers around the compute core.

These functions are designed to be called from a Bash script, a skill, or
the Claude Agent SDK tool layer. All inputs and outputs are plain Python
(dicts, lists, floats, strings); numpy arrays never leave the session.

Heavy artifacts (Monte Carlo arrays) are stored on the session and
referenced by short handles so the LLM context stays small.
"""

from __future__ import annotations

import copy
import dataclasses
import tempfile
from dataclasses import is_dataclass
from typing import Any, Optional

from cvh_cost.core.deterministic import compute_deterministic
from cvh_cost.core.monte_carlo import run_monte_carlo as _core_run_monte_carlo
from cvh_cost.core.reporting import format_text_report
from cvh_cost.agent.session import (
    AnalysisArtifact,
    AssembledParams,
    _to_jsonable,
    get_session,
)


# ----- internal helpers -----

_PARAM_GROUPS = ("condo", "house", "sim", "econ")


def _require_params() -> AssembledParams:
    s = get_session()
    if s.params is None:
        raise ValueError("session.params not assembled — run intake/assemble first")
    return s.params


def _apply_overrides(
    params: AssembledParams,
    overrides: Optional[dict],
    extra: Optional[dict] = None,
) -> AssembledParams:
    """Return a deep-copied AssembledParams with ``overrides`` applied.

    Overrides are a flat dotted-path dict, e.g. ``{"sim.discount_rate": 0.04,
    "condo.monthly_fee": 500}``. ``extra`` is merged on top so callers like
    :func:`run_monte_carlo` can layer ``num_sims`` without mutating the input.
    """
    merged: dict[str, Any] = {}
    if overrides:
        merged.update(overrides)
    if extra:
        merged.update(extra)

    if not merged:
        # Still deep-copy to avoid any shared-state surprises.
        return copy.deepcopy(params)

    # Group overrides by top-level field, validate paths, then dataclasses.replace
    # each group once.
    grouped: dict[str, dict[str, Any]] = {g: {} for g in _PARAM_GROUPS}
    for path, value in merged.items():
        if "." not in path:
            raise ValueError(f"unknown param path: {path}")
        group, _, field_name = path.partition(".")
        if group not in grouped:
            raise ValueError(f"unknown param path: {path}")
        target = getattr(params, group)
        if not is_dataclass(target):
            raise ValueError(f"unknown param path: {path}")
        valid_fields = {f.name for f in dataclasses.fields(target)}
        if field_name not in valid_fields:
            raise ValueError(f"unknown param path: {path}")
        grouped[group][field_name] = value

    new_groups: dict[str, Any] = {}
    for group in _PARAM_GROUPS:
        original = getattr(params, group)
        # Deep-copy so mutable fields (lists of events, etc.) aren't shared.
        new_groups[group] = (
            dataclasses.replace(copy.deepcopy(original), **grouped[group])
            if grouped[group]
            else copy.deepcopy(original)
        )

    return AssembledParams(
        condo=new_groups["condo"],
        house=new_groups["house"],
        sim=new_groups["sim"],
        econ=new_groups["econ"],
        provenance=dict(params.provenance),
    )


def _det_to_dict(det: Any) -> dict[str, float]:
    return {f.name: float(getattr(det, f.name)) for f in dataclasses.fields(det)}


def _mc_summary_to_dict(summary: Any) -> dict[str, float]:
    return {f.name: float(getattr(summary, f.name)) for f in dataclasses.fields(summary)}


def _summarize_mc(mc: Any, num_sims: int) -> dict[str, Any]:
    return {
        "condo": _mc_summary_to_dict(mc.condo_summary),
        "house": _mc_summary_to_dict(mc.house_summary),
        "diff": _mc_summary_to_dict(mc.diff_summary),
        "prob_house_more_expensive": float(mc.prob_house_more_expensive),
        "num_sims": int(num_sims),
    }


# ----- public tool surface -----

def assemble_params_snapshot() -> dict:
    """Return a JSON-safe view of ``session.params`` (or ``{}`` if not set).

    Includes the provenance map. Used by Claude before kicking off a heavy
    Monte Carlo so the user can review what's about to be computed.
    """
    s = get_session()
    if s.params is None:
        return {}
    snapshot: dict = _to_jsonable(s.params)
    return snapshot


def run_deterministic(overrides: Optional[dict] = None) -> dict:
    """Run :func:`compute_deterministic` with optional dotted-path overrides.

    The session's params are not mutated. The result is stored as an
    artifact and a handle is returned alongside the JSON-safe result.
    """
    base = _require_params()
    params = _apply_overrides(base, overrides)

    det = compute_deterministic(params.condo, params.house, params.sim, params.econ)

    s = get_session()
    handle = s.next_handle("det")
    artifact = AnalysisArtifact(
        handle=handle,
        kind="deterministic",
        params=params,
        deterministic=det,
    )
    s.store_artifact(artifact)
    s.log("run_deterministic", handle=handle, overrides=dict(overrides or {}))
    return {"handle": handle, "result": _det_to_dict(det)}


def run_monte_carlo(
    overrides: Optional[dict] = None,
    num_sims: Optional[int] = None,
) -> dict:
    """Run :func:`cvh_cost.core.monte_carlo.run_monte_carlo` and store arrays.

    ``num_sims`` is treated as a convenience override for ``sim.num_sims``.
    Returns the handle plus a small summary; the full PV arrays stay on the
    session artifact so they never enter the LLM context.
    """
    base = _require_params()
    extra = {"sim.num_sims": int(num_sims)} if num_sims is not None else None
    params = _apply_overrides(base, overrides, extra=extra)

    mc = _core_run_monte_carlo(params.condo, params.house, params.sim, params.econ)

    s = get_session()
    handle = s.next_handle("mc")
    artifact = AnalysisArtifact(
        handle=handle,
        kind="monte_carlo",
        params=params,
        monte_carlo=mc,
    )
    s.store_artifact(artifact)
    s.log(
        "run_monte_carlo",
        handle=handle,
        overrides=dict(overrides or {}),
        num_sims=int(params.sim.num_sims),
    )
    return {
        "handle": handle,
        "summary": _summarize_mc(mc, num_sims=params.sim.num_sims),
    }


def summarize_results(handle: str) -> str:
    """Return a formatted text report for the artifact behind ``handle``."""
    s = get_session()
    if handle not in s.artifacts:
        raise KeyError(f"unknown handle: {handle}")
    art = s.artifacts[handle]
    return format_text_report(
        art.deterministic,
        art.monte_carlo,
        art.params.sim,
        art.params.econ,
    )


def plot_results(
    handle: str,
    kind: str = "diff",
    out_path: Optional[str] = None,
) -> str:
    """Render a plot for a Monte Carlo artifact and return its path.

    ``kind`` is one of:
      - ``"diff"``: histogram of the house-minus-condo PV difference.
      - ``"distributions"``: side-by-side condo/house PV histograms.

    Uses the matplotlib ``Agg`` backend so it works in a headless run.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from cvh_cost.core.reporting import plot_diff_distribution, plot_pv_distributions

    s = get_session()
    if handle not in s.artifacts:
        raise KeyError(f"unknown handle: {handle}")
    art = s.artifacts[handle]
    if art.monte_carlo is None:
        raise ValueError(f"handle {handle} is not a Monte Carlo artifact")

    if kind == "diff":
        fig = plot_diff_distribution(art.monte_carlo)
    elif kind == "distributions":
        fig = plot_pv_distributions(art.monte_carlo)
    else:
        raise ValueError(f"unknown plot kind: {kind!r} (expected 'diff' or 'distributions')")

    if out_path is None:
        fd, out_path = tempfile.mkstemp(suffix=".png", prefix=f"cvh_{handle}_{kind}_")
        # Close the dangling fd; matplotlib will write to the path.
        import os
        os.close(fd)

    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def list_artifacts() -> list[dict]:
    """Return one-line descriptors for every artifact on the session."""
    s = get_session()
    out: list[dict] = []
    for handle, art in s.artifacts.items():
        if art.kind == "deterministic" and art.deterministic is not None:
            summary = (
                f"diff_pv=${art.deterministic.diff_pv:,.0f} "
                f"(years={art.params.sim.years}, r={art.params.sim.discount_rate:.2%})"
            )
        elif art.kind == "monte_carlo" and art.monte_carlo is not None:
            mc = art.monte_carlo
            summary = (
                f"mean_diff=${mc.diff_summary.mean:,.0f}, "
                f"P(house>condo)={mc.prob_house_more_expensive:.0%}, "
                f"n={int(mc.condo_pv.shape[0])}"
            )
        else:
            summary = "(empty artifact)"
        out.append({"handle": handle, "kind": art.kind, "summary": summary})
    return out


__all__ = [
    "assemble_params_snapshot",
    "run_deterministic",
    "run_monte_carlo",
    "summarize_results",
    "plot_results",
    "list_artifacts",
]
