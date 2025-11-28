# Configuration Schema Reference

This document describes the YAML configuration format for the `cvh_cost` package.

## Top-Level Structure

```yaml
years: <integer>           # Required: Analysis horizon in years
discount_rate: <float>     # Required: Annual discount rate (e.g., 0.03 for 3%)

economic:                  # Optional: Economic assumptions
  mode: <string>           # "real" or "nominal" (default: "real")
  inflation_rate: <float>  # Expected inflation (default: 0.0)

condo:                     # Required: Condo parameters
  monthly_fee: <float>     # Required: Monthly HOA/condo fee
  fee_escalation_rate: <float>  # Optional: Annual fee growth (default: 0.0)
  events: <list>           # Optional: One-time events
  other_recurring_costs: <list>  # Optional: Other annual costs

house:                     # Required: House parameters
  initial_value: <float>   # Required: House value at year 0
  value_growth_rate: <float>    # Optional: Annual value growth (default: 0.0)
  annual_maintenance_rate: <float>  # Optional: Maintenance as % of value (default: 0.0)
  events: <list>           # Optional: One-time events
  other_recurring_costs: <list>  # Optional: Other annual costs

simulation:                # Optional: Monte Carlo settings
  num_sims: <integer>      # Number of simulations (default: 10000)
  random_seed: <integer>   # RNG seed (default: 42)
  house_maintenance_vol: <float>  # Maintenance volatility (default: 0.0)
  condo_fee_vol: <float>   # Fee volatility (default: 0.0)
```

## Event Configuration

```yaml
events:
  - name: <string>              # Required: Event name
    base_cost: <float>          # Required: Expected cost
    expected_year: <integer>    # Required: Typical year of occurrence
    timing_std_years: <float>   # Optional: Timing uncertainty (default: 0.0)
    min_year: <integer>         # Optional: Earliest possible year (default: 1)
    max_year: <integer>         # Optional: Latest possible year (default: years)
    cost_vol: <float>           # Optional: Cost volatility (default: 0.0)
```

## Recurring Other Cost Configuration

```yaml
other_recurring_costs:
  - name: <string>              # Required: Cost name
    annual_amount: <float>      # Required: Annual amount
    escalation_rate: <float>    # Optional: Annual growth (default: 0.0)
```

## Example: Simple Configuration

```yaml
# Simple 20-year comparison
years: 20
discount_rate: 0.03

condo:
  monthly_fee: 400
  fee_escalation_rate: 0.02

house:
  initial_value: 400000
  annual_maintenance_rate: 0.015
  events:
    - name: "roof"
      base_cost: 12000
      expected_year: 15

simulation:
  num_sims: 10000
  random_seed: 42
```

## Example: Advanced Configuration

```yaml
# Comprehensive 25-year analysis
years: 25
discount_rate: 0.035

economic:
  mode: real
  inflation_rate: 0.025

condo:
  monthly_fee: 550
  fee_escalation_rate: 0.03
  events:
    - name: "special_assessment_exterior"
      base_cost: 8000
      expected_year: 10
      timing_std_years: 2
      min_year: 5
      max_year: 15
      cost_vol: 0.30
    - name: "special_assessment_amenities"
      base_cost: 5000
      expected_year: 18
      timing_std_years: 2
      cost_vol: 0.25
  other_recurring_costs:
    - name: "unit_insurance"
      annual_amount: 600
      escalation_rate: 0.02
    - name: "parking_fee"
      annual_amount: 1200
      escalation_rate: 0.01

house:
  initial_value: 500000
  value_growth_rate: 0.02
  annual_maintenance_rate: 0.015
  events:
    - name: "roof_replacement"
      base_cost: 15000
      expected_year: 20
      timing_std_years: 3
      min_year: 15
      max_year: 25
      cost_vol: 0.25
    - name: "hvac_replacement"
      base_cost: 8000
      expected_year: 15
      timing_std_years: 2
      cost_vol: 0.20
    - name: "water_heater"
      base_cost: 2000
      expected_year: 12
      timing_std_years: 2
      cost_vol: 0.15
  other_recurring_costs:
    - name: "home_insurance"
      annual_amount: 1800
      escalation_rate: 0.03
    - name: "landscaping"
      annual_amount: 2400
      escalation_rate: 0.02

simulation:
  num_sims: 20000
  random_seed: 12345
  house_maintenance_vol: 0.25
  condo_fee_vol: 0.08
```

## Field Reference

### Rates and Percentages

All rates are expressed as decimals:

- 3% = 0.03
- 1.5% = 0.015
- 25% = 0.25

### Volatility Parameters

Volatility represents the standard deviation of a normal shock applied multiplicatively:

- `cost_actual = cost_base * max(0, 1 + Normal(0, volatility))`
- A volatility of 0.25 means costs can easily vary ±25% from baseline

### Timing Parameters

- `expected_year`: The "typical" year when an event occurs (used in deterministic mode)
- `timing_std_years`: Standard deviation for Monte Carlo timing jitter
- `min_year`, `max_year`: Hard bounds for event timing

### Defaults Summary

| Field | Default |
|-------|---------|
| `economic.mode` | "real" |
| `economic.inflation_rate` | 0.0 |
| `condo.fee_escalation_rate` | 0.0 |
| `house.value_growth_rate` | 0.0 |
| `house.annual_maintenance_rate` | 0.0 |
| `event.timing_std_years` | 0.0 |
| `event.min_year` | 1 |
| `event.max_year` | years |
| `event.cost_vol` | 0.0 |
| `other.escalation_rate` | 0.0 |
| `simulation.num_sims` | 10000 |
| `simulation.random_seed` | 42 |
| `simulation.house_maintenance_vol` | 0.0 |
| `simulation.condo_fee_vol` | 0.0 |

## Validation Rules

The config loader validates:

1. `years >= 1`
2. `discount_rate >= 0`
3. `num_sims >= 1`
4. `condo.monthly_fee >= 0`
5. `house.initial_value >= 0`
6. `house.annual_maintenance_rate` in [0, 1]
7. Each event has `name`, `base_cost`, `expected_year`
8. Each event `expected_year >= 1`
9. Each event `base_cost >= 0`

Validation failures raise `ConfigValidationError` with descriptive messages.
