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
        spec = load_config(str(config_path))
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
        det_result = compute_deterministic(spec)

    if not args.no_monte_carlo:
        mc_result = run_monte_carlo(spec)

    # Output results
    if args.quiet:
        # Print summary line only
        if det_result is not None:
            parts = []
            if det_result.condo is not None:
                parts.append(f"Condo: ${det_result.condo.total_pv:,.0f}")
            if det_result.house is not None:
                parts.append(f"House: ${det_result.house.total_pv:,.0f}")
            if det_result.rent is not None:
                parts.append(f"Rent: ${det_result.rent.total_pv:,.0f}")
            print("  ".join(parts))
        elif mc_result is not None:
            parts = []
            if mc_result.condo is not None:
                parts.append(f"Condo MC mean: ${mc_result.condo.summary.mean:,.0f}")
            if mc_result.house is not None:
                parts.append(f"House MC mean: ${mc_result.house.summary.mean:,.0f}")
            if mc_result.rent is not None:
                parts.append(f"Rent MC mean: ${mc_result.rent.summary.mean:,.0f}")
            print("  ".join(parts))
    else:
        # Print full report — requires deterministic results
        if det_result is not None:
            report = format_text_report(det_result, mc_result, spec.simulation, spec.economic)
            print(report)
        elif mc_result is not None:
            # MC-only mode: build a minimal det result placeholder to satisfy signature
            from .models import ComparisonDeterministicResult
            empty_det = ComparisonDeterministicResult()
            report = format_text_report(empty_det, mc_result, spec.simulation, spec.economic)
            print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
