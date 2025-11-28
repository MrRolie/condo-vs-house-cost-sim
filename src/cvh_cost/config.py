"""
Configuration loading and validation for the cost analysis engine.

This module handles loading YAML configuration files and converting
them into the appropriate dataclass instances.
"""

from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

import yaml

from .models import (
    CondoParams,
    HouseParams,
    SimulationParams,
    EconomicParams,
    EventConfig,
    RecurringOtherCost,
)


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


def _parse_event(event_data: Dict[str, Any], years: int) -> EventConfig:
    """
    Parse an event configuration from YAML data.
    
    Args:
        event_data: Dictionary with event fields
        years: Analysis horizon (for validation)
    
    Returns:
        EventConfig instance
    
    Raises:
        ConfigValidationError: If required fields are missing or invalid
    """
    required = ["name", "base_cost", "expected_year"]
    for field in required:
        if field not in event_data:
            raise ConfigValidationError(f"Event missing required field: {field}")
    
    expected_year = event_data["expected_year"]
    if expected_year < 1:
        raise ConfigValidationError(
            f"Event '{event_data['name']}' has expected_year < 1: {expected_year}"
        )
    
    return EventConfig(
        name=str(event_data["name"]),
        base_cost=float(event_data["base_cost"]),
        expected_year=int(expected_year),
        timing_std_years=float(event_data.get("timing_std_years", 0.0)),
        min_year=int(event_data.get("min_year", 1)),
        max_year=int(event_data["max_year"]) if event_data.get("max_year") is not None else None,
        cost_vol=float(event_data.get("cost_vol", 0.0)),
    )


def _parse_recurring_cost(cost_data: Dict[str, Any]) -> RecurringOtherCost:
    """
    Parse a recurring other cost from YAML data.
    
    Args:
        cost_data: Dictionary with cost fields
    
    Returns:
        RecurringOtherCost instance
    
    Raises:
        ConfigValidationError: If required fields are missing
    """
    required = ["name", "annual_amount"]
    for field in required:
        if field not in cost_data:
            raise ConfigValidationError(f"Recurring cost missing required field: {field}")
    
    return RecurringOtherCost(
        name=str(cost_data["name"]),
        annual_amount=float(cost_data["annual_amount"]),
        escalation_rate=float(cost_data.get("escalation_rate", 0.0)),
    )


def _parse_condo(condo_data: Dict[str, Any], years: int) -> CondoParams:
    """
    Parse condo parameters from YAML data.
    """
    if "monthly_fee" not in condo_data:
        raise ConfigValidationError("Condo section missing required field: monthly_fee")
    
    events = [
        _parse_event(e, years) 
        for e in condo_data.get("events", [])
    ]
    
    other_costs = [
        _parse_recurring_cost(c) 
        for c in condo_data.get("other_recurring_costs", [])
    ]
    
    return CondoParams(
        monthly_fee=float(condo_data["monthly_fee"]),
        fee_escalation_rate=float(condo_data.get("fee_escalation_rate", 0.0)),
        events=events,
        other_recurring_costs=other_costs,
    )


def _parse_house(house_data: Dict[str, Any], years: int) -> HouseParams:
    """
    Parse house parameters from YAML data.
    """
    if "initial_value" not in house_data:
        raise ConfigValidationError("House section missing required field: initial_value")
    
    events = [
        _parse_event(e, years) 
        for e in house_data.get("events", [])
    ]
    
    other_costs = [
        _parse_recurring_cost(c) 
        for c in house_data.get("other_recurring_costs", [])
    ]
    
    return HouseParams(
        initial_value=float(house_data["initial_value"]),
        value_growth_rate=float(house_data.get("value_growth_rate", 0.0)),
        annual_maintenance_rate=float(house_data.get("annual_maintenance_rate", 0.0)),
        events=events,
        other_recurring_costs=other_costs,
    )


def _parse_simulation(sim_data: Optional[Dict[str, Any]], years: int, discount_rate: float) -> SimulationParams:
    """
    Parse simulation parameters from YAML data.
    
    Uses top-level years and discount_rate, with optional overrides from simulation section.
    """
    if sim_data is None:
        sim_data = {}
    
    return SimulationParams(
        years=years,
        discount_rate=discount_rate,
        num_sims=int(sim_data.get("num_sims", 10_000)),
        random_seed=int(sim_data.get("random_seed", 42)),
        house_maintenance_vol=float(sim_data.get("house_maintenance_vol", 0.0)),
        condo_fee_vol=float(sim_data.get("condo_fee_vol", 0.0)),
    )


def _parse_economic(econ_data: Optional[Dict[str, Any]]) -> EconomicParams:
    """
    Parse economic parameters from YAML data.
    """
    if econ_data is None:
        return EconomicParams()
    
    mode = econ_data.get("mode", "real")
    if mode not in ("nominal", "real"):
        raise ConfigValidationError(f"Invalid economic mode: {mode}. Must be 'nominal' or 'real'.")
    
    return EconomicParams(
        mode=mode,  # type: ignore
        inflation_rate=float(econ_data.get("inflation_rate", 0.0)),
    )


def validate_config(
    condo: CondoParams,
    house: HouseParams,
    sim: SimulationParams,
    econ: EconomicParams,
) -> List[str]:
    """
    Validate configuration parameters.
    
    Returns a list of warning/error messages. Empty list means valid.
    """
    warnings = []
    
    if sim.years < 1:
        warnings.append(f"years must be >= 1, got {sim.years}")
    
    if sim.discount_rate < 0:
        warnings.append(f"discount_rate should be >= 0, got {sim.discount_rate}")
    
    if sim.num_sims < 1:
        warnings.append(f"num_sims must be >= 1, got {sim.num_sims}")
    
    if condo.monthly_fee < 0:
        warnings.append(f"condo.monthly_fee should be >= 0, got {condo.monthly_fee}")
    
    if house.initial_value < 0:
        warnings.append(f"house.initial_value should be >= 0, got {house.initial_value}")
    
    if house.annual_maintenance_rate < 0 or house.annual_maintenance_rate > 1:
        warnings.append(
            f"house.annual_maintenance_rate should be in [0, 1], got {house.annual_maintenance_rate}"
        )
    
    # Validate events
    for event in condo.events + house.events:
        if event.expected_year > sim.years:
            warnings.append(
                f"Event '{event.name}' has expected_year ({event.expected_year}) > years ({sim.years})"
            )
        if event.base_cost < 0:
            warnings.append(f"Event '{event.name}' has negative base_cost: {event.base_cost}")
    
    return warnings


def load_config(
    path: str,
) -> Tuple[CondoParams, HouseParams, SimulationParams, EconomicParams]:
    """
    Load configuration from a YAML file.
    
    Args:
        path: Path to the YAML configuration file
    
    Returns:
        Tuple of (CondoParams, HouseParams, SimulationParams, EconomicParams)
    
    Raises:
        ConfigValidationError: If required fields are missing or invalid
        FileNotFoundError: If the config file doesn't exist
        yaml.YAMLError: If the YAML is malformed
    
    Example:
        >>> condo, house, sim, econ = load_config("examples/basic_config.yaml")
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    if data is None:
        raise ConfigValidationError("Empty configuration file")
    
    # Required top-level fields
    if "years" not in data:
        raise ConfigValidationError("Missing required field: years")
    if "discount_rate" not in data:
        raise ConfigValidationError("Missing required field: discount_rate")
    if "condo" not in data:
        raise ConfigValidationError("Missing required section: condo")
    if "house" not in data:
        raise ConfigValidationError("Missing required section: house")
    
    years = int(data["years"])
    discount_rate = float(data["discount_rate"])
    
    condo = _parse_condo(data["condo"], years)
    house = _parse_house(data["house"], years)
    sim = _parse_simulation(data.get("simulation"), years, discount_rate)
    econ = _parse_economic(data.get("economic"))
    
    # Validate
    warnings = validate_config(condo, house, sim, econ)
    if warnings:
        raise ConfigValidationError("Configuration validation failed:\n" + "\n".join(warnings))
    
    return condo, house, sim, econ


def load_config_dict(data: Dict[str, Any]) -> Tuple[CondoParams, HouseParams, SimulationParams, EconomicParams]:
    """
    Load configuration from a dictionary (useful for programmatic config).
    
    Args:
        data: Configuration dictionary (same structure as YAML)
    
    Returns:
        Tuple of (CondoParams, HouseParams, SimulationParams, EconomicParams)
    """
    if "years" not in data:
        raise ConfigValidationError("Missing required field: years")
    if "discount_rate" not in data:
        raise ConfigValidationError("Missing required field: discount_rate")
    if "condo" not in data:
        raise ConfigValidationError("Missing required section: condo")
    if "house" not in data:
        raise ConfigValidationError("Missing required section: house")
    
    years = int(data["years"])
    discount_rate = float(data["discount_rate"])
    
    condo = _parse_condo(data["condo"], years)
    house = _parse_house(data["house"], years)
    sim = _parse_simulation(data.get("simulation"), years, discount_rate)
    econ = _parse_economic(data.get("economic"))
    
    warnings = validate_config(condo, house, sim, econ)
    if warnings:
        raise ConfigValidationError("Configuration validation failed:\n" + "\n".join(warnings))
    
    return condo, house, sim, econ
