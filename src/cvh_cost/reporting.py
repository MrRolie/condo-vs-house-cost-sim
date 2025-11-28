"""
Reporting and visualization utilities.

This module provides functions for generating text reports and
plots from the analysis results.
"""

from typing import Optional

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.figure

from .models import DeterministicResult, MonteCarloResult, SimulationParams
from .pv import pv_to_monthly_savings


def format_text_report(
    det: Optional[DeterministicResult],
    mc: Optional[MonteCarloResult],
    sim: SimulationParams,
) -> str:
    """
    Generate a formatted text report of the analysis results.
    
    Args:
        det: Deterministic results (can be None if not computed)
        mc: Monte Carlo results (can be None if not computed)
        sim: Simulation parameters
    
    Returns:
        Formatted string report
    """
    lines = []
    lines.append("=" * 60)
    lines.append("CONDO VS HOUSE OWNERSHIP COST ANALYSIS")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Analysis horizon: {sim.years} years")
    lines.append(f"Discount rate: {sim.discount_rate:.2%}")
    lines.append("")
    lines.append("Note: All values are Present Value (PV) of ownership costs.")
    lines.append("      Higher PV = more expensive over the analysis period.")
    lines.append("")
    
    if det is not None:
        # Calculate monthly savings needed
        condo_monthly = pv_to_monthly_savings(det.condo_pv_total, sim.discount_rate, sim.years)
        house_monthly = pv_to_monthly_savings(det.house_pv_total, sim.discount_rate, sim.years)
        diff_monthly = pv_to_monthly_savings(abs(det.diff_pv), sim.discount_rate, sim.years)
        
        lines.append("-" * 40)
        lines.append("DETERMINISTIC RESULTS")
        lines.append("-" * 40)
        lines.append("")
        lines.append("Condo Ownership Costs (PV):")
        lines.append(f"  Monthly fees:     ${det.condo_pv_base:>12,.0f}")
        lines.append(f"  One-time events:  ${det.condo_pv_events:>12,.0f}")
        lines.append(f"  Other recurring:  ${det.condo_pv_other:>12,.0f}")
        lines.append(f"  TOTAL PV:         ${det.condo_pv_total:>12,.0f}")
        lines.append(f"  → Equivalent monthly savings: ${condo_monthly:>8,.0f}/mo")
        lines.append("")
        lines.append("House Ownership Costs (PV):")
        lines.append(f"  Maintenance:      ${det.house_pv_base:>12,.0f}")
        lines.append(f"  One-time events:  ${det.house_pv_events:>12,.0f}")
        lines.append(f"  Other recurring:  ${det.house_pv_other:>12,.0f}")
        lines.append(f"  TOTAL PV:         ${det.house_pv_total:>12,.0f}")
        lines.append(f"  → Equivalent monthly savings: ${house_monthly:>8,.0f}/mo")
        lines.append("")
        lines.append(f"Cost Difference (House - Condo): ${det.diff_pv:>12,.0f}")
        if det.diff_pv > 0:
            lines.append(f"  → House costs ${det.diff_pv:,.0f} more (PV)")
            lines.append(f"  → You'd need ~${diff_monthly:,.0f}/mo extra savings for house")
        elif det.diff_pv < 0:
            lines.append(f"  → Condo costs ${-det.diff_pv:,.0f} more (PV)")
            lines.append(f"  → You'd need ~${diff_monthly:,.0f}/mo extra savings for condo")
        else:
            lines.append("  → Costs are equal")
        lines.append("")
    
    if mc is not None:
        # Calculate monthly savings for MC results
        condo_monthly_mc = pv_to_monthly_savings(mc.condo_summary.mean, sim.discount_rate, sim.years)
        house_monthly_mc = pv_to_monthly_savings(mc.house_summary.mean, sim.discount_rate, sim.years)
        diff_monthly_mc = pv_to_monthly_savings(abs(mc.diff_summary.mean), sim.discount_rate, sim.years)
        
        lines.append("-" * 40)
        lines.append("MONTE CARLO RESULTS")
        lines.append("-" * 40)
        lines.append(f"Simulations: {sim.num_sims:,}")
        lines.append("")
        
        lines.append("Condo Ownership Costs (PV Distribution):")
        lines.append(f"  Mean:      ${mc.condo_summary.mean:>12,.0f}  (~${condo_monthly_mc:,.0f}/mo)")
        lines.append(f"  Std Dev:   ${mc.condo_summary.std:>12,.0f}")
        lines.append(f"  5th %:     ${mc.condo_summary.p5:>12,.0f}")
        lines.append(f"  Median:    ${mc.condo_summary.p50:>12,.0f}")
        lines.append(f"  95th %:    ${mc.condo_summary.p95:>12,.0f}")
        lines.append("")
        
        lines.append("House Ownership Costs (PV Distribution):")
        lines.append(f"  Mean:      ${mc.house_summary.mean:>12,.0f}  (~${house_monthly_mc:,.0f}/mo)")
        lines.append(f"  Std Dev:   ${mc.house_summary.std:>12,.0f}")
        lines.append(f"  5th %:     ${mc.house_summary.p5:>12,.0f}")
        lines.append(f"  Median:    ${mc.house_summary.p50:>12,.0f}")
        lines.append(f"  95th %:    ${mc.house_summary.p95:>12,.0f}")
        lines.append("")
        
        lines.append("Cost Difference Distribution (House - Condo):")
        lines.append(f"  Mean:      ${mc.diff_summary.mean:>12,.0f}  (~${diff_monthly_mc:,.0f}/mo diff)")
        lines.append(f"  Std Dev:   ${mc.diff_summary.std:>12,.0f}")
        lines.append(f"  5th %:     ${mc.diff_summary.p5:>12,.0f}")
        lines.append(f"  Median:    ${mc.diff_summary.p50:>12,.0f}")
        lines.append(f"  95th %:    ${mc.diff_summary.p95:>12,.0f}")
        lines.append("")
        
        lines.append(f"Probability (House costs more): {mc.prob_house_more_expensive:.1%}")
        lines.append("")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)


def plot_diff_distribution(
    mc: MonteCarloResult,
    title: str = "Ownership Cost Difference: House vs Condo",
    bins: int = 50,
    figsize: tuple[float, float] = (10, 6),
) -> matplotlib.figure.Figure:
    """
    Plot a histogram of the cost difference distribution (House PV - Condo PV).
    
    Args:
        mc: Monte Carlo results
        title: Plot title
        bins: Number of histogram bins
        figsize: Figure size (width, height) in inches
    
    Returns:
        matplotlib Figure object
    """
    fig, ax = plt.subplots(figsize=figsize)
    
    # Plot histogram
    ax.hist(mc.diff_pv, bins=bins, edgecolor='black', alpha=0.7, color='steelblue')
    
    # Add vertical line at zero (break-even)
    ax.axvline(x=0, color='red', linestyle='--', linewidth=2, label='Break-even (costs equal)')
    
    # Add vertical line at mean
    ax.axvline(x=mc.diff_summary.mean, color='green', linestyle='-', linewidth=2, 
               label=f'Mean: ${mc.diff_summary.mean:,.0f}')
    
    # Add vertical lines for percentiles
    ax.axvline(x=mc.diff_summary.p5, color='orange', linestyle=':', linewidth=1.5,
               label=f'5th %: ${mc.diff_summary.p5:,.0f}')
    ax.axvline(x=mc.diff_summary.p95, color='orange', linestyle=':', linewidth=1.5,
               label=f'95th %: ${mc.diff_summary.p95:,.0f}')
    
    ax.set_xlabel('Cost Difference (House Cost PV − Condo Cost PV) [$]')
    ax.set_ylabel('Frequency')
    ax.set_title(title)
    ax.legend(loc='upper right')
    
    # Format x-axis with dollar amounts
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    
    # Add annotation for probability
    prob_text = f'P(House costs more) = {mc.prob_house_more_expensive:.1%}'
    ax.annotate(prob_text, xy=(0.02, 0.98), xycoords='axes fraction',
                fontsize=11, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=1.0))
    
    # Add explanatory note
    note_text = 'Positive = House more expensive\nNegative = Condo more expensive'
    ax.annotate(note_text, xy=(0.02, 0.88), xycoords='axes fraction',
                fontsize=9, verticalalignment='top', color='gray')
    
    plt.tight_layout()
    return fig


def plot_pv_distributions(
    mc: MonteCarloResult,
    title: str = "Ownership Cost PV Distributions",
    bins: int = 50,
    figsize: tuple[float, float] = (12, 5),
) -> matplotlib.figure.Figure:
    """
    Plot side-by-side histograms of condo and house cost PV distributions.
    
    Args:
        mc: Monte Carlo results
        title: Plot title
        bins: Number of histogram bins
        figsize: Figure size (width, height) in inches
    
    Returns:
        matplotlib Figure object
    """
    fig, axes = plt.subplots(1, 2, figsize=figsize)
    
    # Condo distribution
    axes[0].hist(mc.condo_pv, bins=bins, edgecolor='black', alpha=0.7, color='royalblue')
    axes[0].axvline(x=mc.condo_summary.mean, color='red', linestyle='-', linewidth=2,
                    label=f'Mean: ${mc.condo_summary.mean:,.0f}')
    axes[0].set_xlabel('Condo Ownership Cost PV [$]')
    axes[0].set_ylabel('Frequency')
    axes[0].set_title('Condo Ownership Costs (PV)')
    axes[0].legend()
    axes[0].xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x/1000:.0f}k'))
    
    # House distribution
    axes[1].hist(mc.house_pv, bins=bins, edgecolor='black', alpha=0.7, color='forestgreen')
    axes[1].axvline(x=mc.house_summary.mean, color='red', linestyle='-', linewidth=2,
                    label=f'Mean: ${mc.house_summary.mean:,.0f}')
    axes[1].set_xlabel('House Ownership Cost PV [$]')
    axes[1].set_ylabel('Frequency')
    axes[1].set_title('House Ownership Costs (PV)')
    axes[1].legend()
    axes[1].xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x/1000:.0f}k'))
    
    fig.suptitle(title + '\n(Higher PV = More Expensive)', fontsize=14)
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
