# API Contract

This document describes the public API of the `cvh_cost` package.

## Core Functions

### `compute_deterministic()`

Computes deterministic present values for condo and house ownership costs.

```python
def compute_deterministic(
    condo: CondoParams,
    house: HouseParams,
    sim: SimulationParams,
    econ: EconomicParams,
) -> DeterministicResult:
```

**Parameters:**

- `condo`: Condo cost parameters
- `house`: House cost parameters
- `sim`: Simulation parameters (uses `years`, `discount_rate`)
- `econ`: Economic parameters (reserved for future use)

**Returns:** `DeterministicResult` with PV breakdowns

**Side effects:** None (pure function)

---

### `run_monte_carlo()`

Runs Monte Carlo simulation for cost comparison.

```python
def run_monte_carlo(
    condo: CondoParams,
    house: HouseParams,
    sim: SimulationParams,
    econ: EconomicParams,
) -> MonteCarloResult:
```

**Parameters:**

- `condo`: Condo cost parameters
- `house`: House cost parameters
- `sim`: Simulation parameters (uses all fields including volatilities)
- `econ`: Economic parameters (reserved for future use)

**Returns:** `MonteCarloResult` with arrays and summaries

**Side effects:** None (pure function, uses seeded RNG)

---

### `load_config()`

Loads configuration from a YAML file.

```python
def load_config(
    path: str,
) -> Tuple[CondoParams, HouseParams, SimulationParams, EconomicParams]:
```

**Parameters:**

- `path`: Path to YAML configuration file

**Returns:** Tuple of (CondoParams, HouseParams, SimulationParams, EconomicParams)

**Raises:**

- `FileNotFoundError`: If config file doesn't exist
- `ConfigValidationError`: If validation fails
- `yaml.YAMLError`: If YAML is malformed

---

## Data Classes

### `CondoParams`

```python
@dataclass
class CondoParams:
    monthly_fee: float
    fee_escalation_rate: float = 0.0
    events: List[EventConfig] = field(default_factory=list)
    other_recurring_costs: List[RecurringOtherCost] = field(default_factory=list)
```

### `HouseParams`

```python
@dataclass
class HouseParams:
    initial_value: float
    value_growth_rate: float = 0.0
    annual_maintenance_rate: float = 0.0
    events: List[EventConfig] = field(default_factory=list)
    other_recurring_costs: List[RecurringOtherCost] = field(default_factory=list)
```

### `SimulationParams`

```python
@dataclass
class SimulationParams:
    years: int                          # Analysis horizon
    discount_rate: float                # Annual discount rate
    num_sims: int = 10_000              # Number of Monte Carlo simulations
    random_seed: int = 42               # RNG seed for reproducibility
    house_maintenance_vol: float = 0.0  # Std dev for house maintenance shocks
    condo_fee_vol: float = 0.0          # Std dev for condo fee shocks
```

### `EconomicParams`

```python
@dataclass
class EconomicParams:
    mode: Literal["nominal", "real"] = "real"
    inflation_rate: float = 0.0
```

### `EventConfig`

```python
@dataclass
class EventConfig:
    name: str
    base_cost: float
    expected_year: int
    timing_std_years: float = 0.0
    min_year: int = 1
    max_year: Optional[int] = None  # Defaults to sim.years
    cost_vol: float = 0.0
```

### `RecurringOtherCost`

```python
@dataclass
class RecurringOtherCost:
    name: str
    annual_amount: float
    escalation_rate: float = 0.0
```

---

## Result Classes

### `DeterministicResult`

```python
@dataclass
class DeterministicResult:
    condo_pv_base: float      # PV of monthly fees
    condo_pv_events: float    # PV of one-time events
    condo_pv_other: float     # PV of other recurring costs
    condo_pv_total: float     # Total condo PV

    house_pv_base: float      # PV of annual maintenance
    house_pv_events: float    # PV of one-time events
    house_pv_other: float     # PV of other recurring costs
    house_pv_total: float     # Total house PV

    diff_pv: float            # house_pv_total - condo_pv_total
```

### `MonteCarloResult`

```python
@dataclass
class MonteCarloResult:
    condo_pv: np.ndarray              # Shape: (num_sims,)
    house_pv: np.ndarray              # Shape: (num_sims,)
    diff_pv: np.ndarray               # Shape: (num_sims,)

    condo_summary: MonteCarloSummary
    house_summary: MonteCarloSummary
    diff_summary: MonteCarloSummary

    prob_house_more_expensive: float  # P(diff_pv > 0)
```

### `MonteCarloSummary`

```python
@dataclass
class MonteCarloSummary:
    mean: float
    std: float
    p5: float   # 5th percentile
    p50: float  # Median
    p95: float  # 95th percentile
```

---

## Reporting Functions

### `format_text_report()`

```python
def format_text_report(
    det: Optional[DeterministicResult],
    mc: Optional[MonteCarloResult],
    sim: SimulationParams,
) -> str:
```

Returns a formatted string report. Either `det` or `mc` can be None.

### `plot_diff_distribution()`

```python
def plot_diff_distribution(
    mc: MonteCarloResult,
    title: str = "House vs Condo Cost Difference Distribution",
    bins: int = 50,
    figsize: tuple[float, float] = (10, 6),
) -> matplotlib.figure.Figure:
```

Returns a matplotlib Figure with histogram of `diff_pv`.

### `plot_pv_distributions()`

```python
def plot_pv_distributions(
    mc: MonteCarloResult,
    title: str = "Present Value Distributions",
    bins: int = 50,
    figsize: tuple[float, float] = (12, 5),
) -> matplotlib.figure.Figure:
```

Returns a matplotlib Figure with side-by-side histograms.

### `plot_sensitivity()`

```python
def plot_sensitivity(
    param_values: list[float],
    probabilities: list[float],
    param_name: str = "Parameter",
    title: str = "Sensitivity Analysis",
    figsize: tuple[float, float] = (8, 5),
) -> matplotlib.figure.Figure:
```

Returns a matplotlib Figure showing how probability changes with a parameter.

---

## PV Utility Functions

Low-level functions for present value calculations:

```python
def pv_single(cost: float, rate: float, year: int) -> float
def pv_annuity(payment: float, rate: float, n_years: int) -> float
def pv_growth_annuity(payment: float, rate: float, growth: float, n_years: int) -> float
def pv_series(costs_by_year: Dict[int, float], rate: float) -> float
```

These are pure functions with no side effects.
