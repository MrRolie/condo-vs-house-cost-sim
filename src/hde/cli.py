"""
Command-line interface for the condo vs house cost analysis tool.

Usage:
    python -m cvh_cost.cli path/to/config.yaml [options]
"""

import argparse
import sys
from pathlib import Path

from .config import load_config, ConfigValidationError
from .deterministic import compute_deterministic
from .monte_carlo import run_monte_carlo
from .reporting import format_text_report


def main() -> int:
    """
    Main entry point for the CLI.
    
    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    parser = argparse.ArgumentParser(
        prog="cvh-cost",
        description="Condo vs House cost analysis with deterministic and Monte Carlo simulation",
    )
    
    parser.add_argument(
        "config",
        type=str,
        help="Path to YAML configuration file",
    )
    
    parser.add_argument(
        "--no-monte-carlo",
        action="store_true",
        help="Skip Monte Carlo simulation (deterministic only)",
    )
    
    parser.add_argument(
        "--no-deterministic",
        action="store_true",
        help="Skip deterministic calculation (Monte Carlo only)",
    )
    
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress detailed output, print only summary line",
    )
    
    args = parser.parse_args()
    
    # Validate config path
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Configuration file not found: {args.config}", file=sys.stderr)
        return 1
    
    # Load configuration
    try:
        condo, house, sim, econ = load_config(str(config_path))
    except ConfigValidationError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        return 1
    
    # Run analysis
    det_result = None
    mc_result = None
    
    if not args.no_deterministic:
        det_result = compute_deterministic(condo, house, sim, econ)
    
    if not args.no_monte_carlo:
        mc_result = run_monte_carlo(condo, house, sim, econ)
    
    # Output results
    if args.quiet:
        # Print summary line only
        parts = []
        if det_result is not None:
            parts.append(f"Det diff: ${det_result.diff_pv:,.0f}")
        if mc_result is not None:
            parts.append(f"MC mean diff: ${mc_result.diff_summary.mean:,.0f}")
            parts.append(f"P(House>Condo): {mc_result.prob_house_more_expensive:.1%}")
        print(" | ".join(parts))
    else:
        # Print full report
        report = format_text_report(det_result, mc_result, sim, econ)
        print(report)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
