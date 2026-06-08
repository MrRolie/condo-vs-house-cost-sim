# Architecture Overview

This document describes the high-level architecture of the `cvh_cost` package, a tool for comparing ownership costs between condos and houses using present value analysis.

## Module Overview

```text
src/cvh_cost/
├── __init__.py       # Package exports
├── models.py         # Dataclasses for parameters and results
├── pv.py             # Present value calculation utilities
├── deterministic.py  # Deterministic PV calculations
├── monte_carlo.py    # Monte Carlo simulation
├── config.py         # YAML configuration loading
├── reporting.py      # Text reports and plotting
└── cli.py            # Command-line interface
```

## Module Responsibilities

### `models.py`

Defines all dataclasses used throughout the package:

- **Parameter classes**: `CondoParams`, `HouseParams`, `SimulationParams`, `EconomicParams`
- **Supporting classes**: `EventConfig`, `RecurringOtherCost`
- **Result classes**: `DeterministicResult`, `MonteCarloResult`, `MonteCarloSummary`

All dataclasses use type hints and have default values where appropriate.

### `pv.py`

Pure functions for present value calculations:

- `pv_single()`: PV of a one-time future cost
- `pv_annuity()`: PV of a constant annuity
- `pv_growth_annuity()`: PV of a growing annuity
- `pv_series()`: PV of costs at specific years
- `pv_recurring_with_escalation()`: Convenience wrapper

These functions are stateless, deterministic, and independent of the domain model.

### `deterministic.py`

Computes PV using fixed parameters:

- `compute_deterministic()`: Main entry point
- Uses `expected_year` for event timing (ignores `timing_std_years`)
- Returns `DeterministicResult` with PV breakdown

### `monte_carlo.py`

Runs simulations with randomness:

- `run_monte_carlo()`: Main entry point
- Applies volatility to annual costs
- Randomizes event timing and costs
- Returns `MonteCarloResult` with arrays and summaries

### `config.py`

Handles YAML configuration:

- `load_config()`: Load from file path
- `load_config_dict()`: Load from dictionary
- Validation and error handling
- `ConfigValidationError` exception

### `reporting.py`

Output generation:

- `format_text_report()`: Generate text report
- `plot_diff_distribution()`: Histogram of difference
- `plot_pv_distributions()`: Side-by-side histograms
- `plot_sensitivity()`: Sensitivity analysis plot

### `cli.py`

Command-line interface:

- `main()`: Entry point
- Supports `--no-monte-carlo`, `--no-deterministic`, `--quiet` flags

## Deterministic vs Monte Carlo Logic

### Deterministic Calculation

1. **Condo fees**:
   - If `fee_escalation_rate == 0`: Use level annuity formula
   - Otherwise: Use growing annuity formula

2. **House maintenance**:
   - `value_t = initial_value * (1 + value_growth_rate)^(t-1)`
   - `maint_t = annual_maintenance_rate * value_t`
   - If `value_growth_rate == 0`: Level annuity
   - Otherwise: Growing annuity

3. **Events**: Use `expected_year` directly (no randomness)

4. **Other costs**: Similar to base costs with escalation

### Monte Carlo Simulation

For each of `num_sims` iterations:

1. **Annual costs**:
   - Compute deterministic base cost
   - If volatility > 0: Apply `cost *= max(0, 1 + Normal(0, vol))`

2. **Event timing** (Option 1: Jitter):
   - If `timing_std_years <= 0`: Use `expected_year` clamped to valid range
   - Otherwise:

     ```python
     y_raw ~ Normal(expected_year, timing_std_years)
     y_clamped = clamp(y_raw, min_year, max_year)
     year = round(y_clamped)
     year = clamp(year, 1, sim.years)
     ```

3. **Event costs**:
   - If `cost_vol <= 0`: Use `base_cost`
   - Otherwise: `cost = base_cost * max(0, 1 + Normal(0, cost_vol))`

4. **Other recurring costs**: Treated deterministically in v1

## Data Flow

```text
YAML Config
    │
    ▼
load_config() ──► (CondoParams, HouseParams, SimulationParams, EconomicParams)
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
        compute_deterministic()           run_monte_carlo()
                    │                               │
                    ▼                               ▼
          DeterministicResult              MonteCarloResult
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
                          format_text_report()
                                    │
                                    ▼
                            Text output / CLI
```

## Design Decisions

### Why Option 1 (Jitter) for Event Timing?

We chose the "jitter around expected year" approach over a hazard-based model because:

1. **Simplicity**: Easy to understand and configure
2. **Intuitive parameters**: Users can specify "expected year" and "uncertainty"
3. **Bounded outcomes**: Events stay within reasonable time bounds
4. **Good enough for v1**: Most users think in terms of "roof in ~15 years"

A hazard-based model could be added later as an alternative timing strategy.

### Why Multiplicative Shocks?

Cost randomness uses `cost * (1 + shock)` because:

1. **Proportional**: 20% volatility means similar relative uncertainty for $1k and $10k costs
2. **Non-negative**: `max(0, 1 + shock)` prevents negative costs
3. **Centered**: Expected value equals base cost when shock ~ Normal(0, σ)

### Why Separate Deterministic and Monte Carlo?

1. **Different use cases**: Quick estimate vs. uncertainty analysis
2. **Validation**: Deterministic serves as sanity check for MC
3. **Performance**: Deterministic is instant; MC may take seconds
4. **Testability**: Can verify each independently

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_pv.py

# Type checking
mypy src
```

## Extending the Package

### Adding New Event Timing Models

1. Add a `timing_model` field to `EventConfig`
2. Create a new timing function in `monte_carlo.py`
3. Dispatch based on `timing_model` in `_sample_event_year()`

### Adding New Cost Components

1. Add fields to `CondoParams` or `HouseParams`
2. Update `deterministic.py` to compute PV
3. Update `monte_carlo.py` to simulate
4. Update `config.py` to parse from YAML
5. Update result dataclasses if needed

### Adding Geographic Tax Rules

This is explicitly a non-goal for v1. If needed later:

1. Create a separate `TaxParams` dataclass
2. Add to `compute_deterministic()` and `run_monte_carlo()`
3. Keep it optional (default = no tax adjustments)
