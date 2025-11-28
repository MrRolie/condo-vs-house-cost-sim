# Condo vs House Cost Simulator

A Python tool for comparing the long-run present value of ownership costs between condos and houses using deterministic and Monte Carlo analysis.

## Features

- **Deterministic PV Analysis**: Calculate present value of ownership costs with fixed parameters
- **Monte Carlo Simulation**: Model uncertainty in costs and timing with configurable volatility
- **Flexible Configuration**: YAML-based configuration for easy scenario definition
- **Library & CLI**: Use as a Python library or via command-line interface
- **Jupyter Notebooks**: Interactive exploration with provided notebooks

## Installation

```bash
# Clone the repository
git clone https://github.com/example/condo-vs-house-cost-sim.git
cd condo-vs-house-cost-sim

# Install in development mode
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"
```

## Quick Start

### As a Library

```python
from cvh_cost.models import CondoParams, HouseParams, SimulationParams, EconomicParams, EventConfig
from cvh_cost.deterministic import compute_deterministic
from cvh_cost.monte_carlo import run_monte_carlo

# Define parameters
condo = CondoParams(monthly_fee=400, fee_escalation_rate=0.02)
house = HouseParams(
    initial_value=400_000,
    annual_maintenance_rate=0.015,
    events=[EventConfig(name="roof", base_cost=12000, expected_year=15)]
)
sim = SimulationParams(years=20, discount_rate=0.03)
econ = EconomicParams()

# Run analysis
det_result = compute_deterministic(condo, house, sim, econ)
mc_result = run_monte_carlo(condo, house, sim, econ)

print(f"Deterministic difference: ${det_result.diff_pv:,.0f}")
print(f"P(House more expensive): {mc_result.prob_house_more_expensive:.1%}")
```

### Via CLI

```bash
# Run with a config file
python -m cvh_cost.cli examples/basic_config.yaml

# Deterministic only
python -m cvh_cost.cli examples/basic_config.yaml --no-monte-carlo
```

### Via Notebooks

See `notebooks/basic_usage.ipynb` for a guided introduction and `notebooks/advanced_usage.ipynb` for advanced scenarios.

## Configuration

Configuration is done via YAML files. See `examples/` for sample configs.

```yaml
years: 20
discount_rate: 0.03

condo:
  monthly_fee: 400
  fee_escalation_rate: 0.02
  events: []

house:
  initial_value: 400000
  annual_maintenance_rate: 0.015
  events:
    - name: "roof"
      base_cost: 12000
      expected_year: 15
      timing_std_years: 2
      cost_vol: 0.25

simulation:
  num_sims: 10000
  random_seed: 42
  house_maintenance_vol: 0.30
  condo_fee_vol: 0.05
```

## Project Structure

```text
condo-vs-house-cost-sim/
├── pyproject.toml          # Package configuration
├── README.md
├── LICENSE
├── src/
│   └── cvh_cost/           # Main package
│       ├── models.py       # Dataclasses for parameters and results
│       ├── pv.py           # Present value calculation utilities
│       ├── deterministic.py # Deterministic PV calculations
│       ├── monte_carlo.py  # Monte Carlo simulation
│       ├── config.py       # YAML config loading
│       ├── reporting.py    # Text reports and plotting
│       └── cli.py          # Command-line interface
├── notebooks/              # Jupyter notebooks
├── examples/               # Example YAML configs
├── tests/                  # Test suite
└── context/                # Documentation for developers
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=cvh_cost

# Type checking
mypy src
```

## Scope and Non-Goals

This tool focuses **strictly on ownership cost analysis**:

✅ Present value of condo fees and house maintenance  
✅ One-time events (roof, HVAC, special assessments)  
✅ Monte Carlo uncertainty modeling  
✅ Configurable scenarios via YAML  

❌ Rent vs buy analysis  
❌ Investment returns or opportunity cost  
❌ Geographic tax rules  
❌ Leverage or mortgage optimization  

## License

MIT License - see [LICENSE](LICENSE) for details.
