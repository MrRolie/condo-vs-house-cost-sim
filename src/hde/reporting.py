"""
Reporting and visualization utilities.

This module provides functions for generating text reports and
plots from the analysis results.
"""

from typing import Dict, Optional

import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
import matplotlib.figure
from matplotlib.figure import Figure

from .models import (
    ComparisonDeterministicResult,
    ComparisonMonteCarloResult,
    AffordabilityReport,
    OptionResult,
    SimulationParams,
    EconomicParams,
)
from .pv import pv_to_monthly_savings


def format_text_report(
    det: ComparisonDeterministicResult,
    mc: Optional[ComparisonMonteCarloResult],
    sim: SimulationParams,
    econ: EconomicParams,
) -> str:
    """
    Generate a formatted text report of the analysis results.

    Args:
        det: Deterministic comparison results
        mc: Monte Carlo comparison results (optional)
        sim: Simulation parameters
        econ: Economic parameters

    Returns:
        Formatted string report
    """
    lines = []

    # Per-option PV totals
    if det.condo is not None:
        lines.append(f"Condo  total PV:  ${det.condo.total_pv:>12,.0f}")
        for k, v in det.condo.breakdown.items():
            lines.append(f"  {k}: ${v:>12,.0f}")
    if det.house is not None:
        lines.append(f"House  total PV:  ${det.house.total_pv:>12,.0f}")
        for k, v in det.house.breakdown.items():
            lines.append(f"  {k}: ${v:>12,.0f}")
    if det.rent is not None:
        lines.append(f"Rent   total PV:  ${det.rent.total_pv:>12,.0f}")
        for k, v in det.rent.breakdown.items():
            lines.append(f"  {k}: ${v:>12,.0f}")

    # Comparison line
    present_det = [
        (name, r)
        for name, r in [("Condo", det.condo), ("House", det.house), ("Rent", det.rent)]
        if r is not None
    ]
    if len(present_det) >= 2:
        cheapest = min(present_det, key=lambda x: x[1].total_pv)
        costliest = max(present_det, key=lambda x: x[1].total_pv)
        diff = costliest[1].total_pv - cheapest[1].total_pv
        lines.append(f"\nCheapest: {cheapest[0]} saves ${diff:,.0f} vs {costliest[0]}")
        # Monthly equivalent (using pv_to_monthly_savings if discount_rate > 0)
        if sim.discount_rate > 0 and sim.years > 0:
            monthly = pv_to_monthly_savings(diff, sim.discount_rate, sim.years)
            lines.append(f"  ≈ ${monthly:,.0f}/month equivalent")

    # Affordability
    if det.income_report is not None:
        rpt = det.income_report
        lines.append(f"\nAffordability (threshold: {rpt.threshold:.0%})")
        for name, ratios, exceeds in [
            ("Rent",  rpt.rent_ratios,  rpt.years_rent_exceeds),
            ("Condo", rpt.condo_ratios, rpt.years_condo_exceeds),
            ("House", rpt.house_ratios, rpt.years_house_exceeds),
        ]:
            if ratios is not None:
                max_ratio = max(ratios)
                exceed_str = str(exceeds) if exceeds else "none"
                lines.append(f"  {name}: max ratio {max_ratio:.1%}  years exceeding: {exceed_str}")

    # MC summary
    if mc is not None:
        lines.append("\nMonte Carlo:")
        for name, opt in [("Condo", mc.condo), ("House", mc.house), ("Rent", mc.rent)]:
            if opt is not None:
                s = opt.summary
                lines.append(
                    f"  {name}: mean ${s.mean:,.0f}  p5 ${s.p5:,.0f}"
                    f"  p50 ${s.p50:,.0f}  p95 ${s.p95:,.0f}"
                )
        probs = [
            (name, prob)
            for name, prob in [
                ("P(condo cheapest)", mc.prob_condo_cheapest),
                ("P(house cheapest)", mc.prob_house_cheapest),
                ("P(rent cheapest)",  mc.prob_rent_cheapest),
            ]
            if prob is not None
        ]
        for label, prob in probs:
            lines.append(f"  {label}: {prob:.1%}")
        if mc.affordability_mc is not None:
            a = mc.affordability_mc
            lines.append(f"  Affordability MC (threshold {a.threshold:.0%}):")
            for name, prob in [
                ("condo", a.prob_condo_exceeds),
                ("house", a.prob_house_exceeds),
                ("rent",  a.prob_rent_exceeds),
            ]:
                if prob is not None:
                    lines.append(f"    P({name} exceeds threshold): {prob:.1%}")

    return "\n".join(lines)


def plot_diff_distribution(
    diff_pvs: npt.NDArray[np.float64],
    title: str = "Diff Distribution (House − Condo PV)",
    bins: int = 50,
    figsize: tuple = (10, 6),
) -> Figure:
    """
    Plot a histogram of a cost-difference distribution.

    Args:
        diff_pvs: Pre-computed array of PV differences (e.g. house_pv - condo_pv)
        title: Plot title
        bins: Number of histogram bins
        figsize: Figure size (width, height) in inches

    Returns:
        matplotlib Figure object
    """
    fig, ax = plt.subplots(figsize=figsize)

    # Summary stats
    mean_val = float(np.mean(diff_pvs))
    p5_val   = float(np.percentile(diff_pvs, 5))
    p95_val  = float(np.percentile(diff_pvs, 95))
    prob_positive = float(np.mean(diff_pvs > 0))

    # Plot histogram
    ax.hist(diff_pvs, bins=bins, edgecolor='black', alpha=0.7, color='steelblue')

    # Add vertical line at zero (break-even)
    ax.axvline(x=0, color='red', linestyle='--', linewidth=2, label='Break-even (costs equal)')

    # Add vertical line at mean
    ax.axvline(x=mean_val, color='green', linestyle='-', linewidth=2,
               label=f'Mean: ${mean_val:,.0f}')

    # Add vertical lines for percentiles
    ax.axvline(x=p5_val, color='orange', linestyle=':', linewidth=1.5,
               label=f'5th %: ${p5_val:,.0f}')
    ax.axvline(x=p95_val, color='orange', linestyle=':', linewidth=1.5,
               label=f'95th %: ${p95_val:,.0f}')

    ax.set_xlabel('Cost Difference [$]')
    ax.set_ylabel('Frequency')
    ax.set_title(title)
    ax.legend(loc='upper right')

    # Format x-axis with dollar amounts
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))

    # Add annotation for probability
    prob_text = f'P(positive) = {prob_positive:.1%}'
    ax.annotate(prob_text, xy=(0.02, 0.98), xycoords='axes fraction',
                fontsize=11, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=1.0))

    # Add explanatory note
    note_text = 'Positive = first option more expensive\nNegative = second option more expensive'
    ax.annotate(note_text, xy=(0.02, 0.88), xycoords='axes fraction',
                fontsize=9, verticalalignment='top', color='gray')

    plt.tight_layout()
    return fig


def plot_pv_distributions(
    option_arrays: Dict[str, npt.NDArray[np.float64]],
    title: str = "PV Distributions by Option",
    bins: int = 50,
    figsize: tuple = (10, 6),
) -> Figure:
    """
    Plot overlapping histograms of PV distributions for multiple housing options.

    Args:
        option_arrays: Dict mapping option name (e.g. "Condo", "House", "Rent") to
                       its array of simulated PV values.
        title: Plot title
        bins: Number of histogram bins
        figsize: Figure size (width, height) in inches

    Returns:
        matplotlib Figure object
    """
    colors = ['royalblue', 'forestgreen', 'darkorange', 'purple', 'crimson']
    fig, ax = plt.subplots(figsize=figsize)

    for (name, arr), color in zip(option_arrays.items(), colors):
        mean_val = float(np.mean(arr))
        ax.hist(arr, bins=bins, edgecolor='black', alpha=0.5, color=color,
                label=f'{name} (mean ${mean_val/1000:.0f}k)')
        ax.axvline(x=mean_val, color=color, linestyle='-', linewidth=2)

    ax.set_xlabel('Ownership Cost PV [$]')
    ax.set_ylabel('Frequency')
    ax.set_title(title + '\n(Higher PV = More Expensive)')
    ax.legend()
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x/1000:.0f}k'))

    plt.tight_layout()
    return fig


def plot_sensitivity(
    param_values: list[float],
    probabilities: list[float],
    param_name: str = "Parameter",
    title: str = "Sensitivity Analysis",
    figsize: tuple[float, float] = (8, 5),
) -> matplotlib.figure.Figure:
    """
    Plot sensitivity of P(House costs more) to a parameter.

    Args:
        param_values: List of parameter values tested
        probabilities: List of corresponding probabilities
        param_name: Name of the parameter (for x-axis label)
        title: Plot title
        figsize: Figure size

    Returns:
        matplotlib Figure object
    """
    fig, ax = plt.subplots(figsize=figsize)

    ax.plot(param_values, probabilities, marker='o', linewidth=2, markersize=8, color='navy')

    ax.set_xlabel(param_name)
    ax.set_ylabel('P(House ownership costs more)')
    ax.set_title(title)

    # Format y-axis as percentage
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:.0%}'))

    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig
