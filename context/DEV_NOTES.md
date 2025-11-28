# Developer Notes

Notes for developers and coding agents working on the `cvh_cost` package.

## Development Setup

```bash
# Clone and install in development mode
git clone <repo>
cd condo-vs-house-cost-sim
pip install -e ".[dev]"

# Verify installation
python -c "from cvh_cost import compute_deterministic; print('OK')"
```

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_pv.py

# Run tests matching a pattern
pytest -k "test_annuity"

# Run with coverage
pytest --cov=cvh_cost --cov-report=html
```

## Type Checking

```bash
# Run mypy on source
mypy src

# Run with stricter settings
mypy src --strict

# Check a specific file
mypy src/cvh_cost/pv.py
```

## Code Style

### General Guidelines

- Use type hints on all public APIs
- No print statements in core logic (pv.py, deterministic.py, monte_carlo.py, config.py)
- Print statements allowed only in cli.py, reporting.py, and notebooks
- Use descriptive variable names over micro-optimizations
- Prefer dataclasses over dicts for structured data

### Naming Conventions

- Functions: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private functions: `_leading_underscore`

### Docstrings

Use Google-style docstrings:

```python
def compute_something(param1: float, param2: int) -> float:
    """
    Brief description.
    
    Longer description if needed.
    
    Args:
        param1: Description of param1
        param2: Description of param2
    
    Returns:
        Description of return value
    
    Raises:
        ValueError: When something is wrong
    """
```

## Testing Conventions

### Test File Organization

- `test_pv.py`: PV utility function tests
- `test_deterministic.py`: Deterministic calculation tests
- `test_monte_carlo.py`: Monte Carlo simulation tests
- `test_config.py`: Configuration loading tests

### Test Naming

```python
def test_<function>_<scenario>():
    """Tests that <function> correctly handles <scenario>."""
```

### Test Patterns

For PV functions, verify against hand-calculated values:

```python
def test_pv_single_basic():
    # $1000 in 5 years at 5% = 1000 / 1.05^5 = 783.53
    result = pv_single(1000, 0.05, 5)
    assert abs(result - 783.53) < 0.01
```

For Monte Carlo, verify statistical properties:

```python
def test_mc_mean_close_to_deterministic():
    # With zero volatility, MC mean should equal deterministic
    ...
    assert abs(mc.diff_summary.mean - det.diff_pv) < tolerance
```

## Design Decisions and Trade-offs

### Why Jitter Instead of Hazard Model?

The current event timing uses a "jitter around expected year" approach:

```text
year ~ Normal(expected_year, timing_std_years), clamped to [min_year, max_year]
```

Alternatives considered:

1. **Hazard/survival model**: Events occur with probability p(t) each year until they happen
   - More realistic for things like "roof fails at some point"
   - More complex to configure
   - Reserved for future extension

2. **Discrete distribution**: User specifies P(year=10)=0.3, P(year=12)=0.5, etc.
   - Very flexible
   - Tedious to configure
   - Not implemented

The jitter model was chosen for v1 because:

- Simple to understand
- Easy to configure (just expected_year and uncertainty)
- Good enough for most use cases

### Why Multiplicative Shocks?

Cost uncertainty is modeled as:

```python
cost = base_cost * max(0, 1 + Normal(0, vol))
```

Alternatives considered:

1. **Additive shocks**: `cost = base_cost + Normal(0, vol_dollars)`
   - Requires vol in dollars, less intuitive
   - Same absolute uncertainty for $1k and $100k costs

2. **Lognormal**: `cost = base_cost * exp(Normal(0, vol))`
   - Never negative naturally
   - Slightly harder to interpret vol

The multiplicative normal was chosen because:

- Proportional uncertainty (20% vol means ±20% for any base cost)
- Simple to configure
- `max(0, ...)` handles the rare negative case

### Why Other Costs Are Deterministic in v1?

"Other recurring costs" (insurance, landscaping, etc.) don't have volatility in the current implementation. This was intentional:

1. Simplifies the model
2. These costs are typically more predictable than maintenance
3. Can be added later without breaking changes

To add volatility for other costs:

1. Add `other_cost_vol` to `SimulationParams`
2. Apply shocks in `_simulate_condo_pv_once()` and `_simulate_house_pv_once()`

### Why Separate EconomicParams?

`EconomicParams` exists but is mostly unused in v1. It's there for:

1. Future extension (nominal vs real rate conversion)
2. Documentation of user assumptions
3. Semantic clarity

The user is responsible for providing consistent parameters (e.g., if mode is "real", discount_rate should be a real rate).

## Common Pitfalls

### Year Indexing

Years are 1-indexed:

- Year 1 = one year from now
- Year 0 = today (not used)
- Events with `expected_year=0` are clamped to year 1

### Annuity Timing

The growing annuity formula assumes:

- First payment at year 1
- Payment grows each subsequent year
- `pv_growth_annuity(100, r, g, n)` means year 1 payment is 100, year 2 is 100*(1+g), etc.

For condo fees with escalation:

- `annual_fee = monthly_fee * 12` (year 0 base)
- `first_year_fee = annual_fee * (1 + escalation_rate)` (year 1 payment)

### House Maintenance

House value in year t:

```python
value_t = initial_value * (1 + value_growth_rate)**(t-1)
```

Note: Year 1 uses `(t-1)=0`, so year 1 maintenance is based on initial_value.

## Extending the Package

### Adding a New Cost Component

1. Add field to `CondoParams` or `HouseParams`
2. Update `_compute_*_pv()` in `deterministic.py`
3. Update `_simulate_*_pv_once()` in `monte_carlo.py`
4. Update `_parse_condo()` or `_parse_house()` in `config.py`
5. Update result dataclass if needed
6. Add tests
7. Update documentation

### Adding a New Timing Model

1. Add `timing_model: Literal["jitter", "hazard"] = "jitter"` to `EventConfig`
2. Create `_sample_event_year_hazard()` function
3. Add dispatch in `_sample_event_year()` based on model
4. Update config parsing and validation
5. Add tests
6. Update documentation

### Adding CLI Options

1. Add argument in `cli.py` using argparse
2. Handle in `main()` function
3. Update help text
4. Update README
