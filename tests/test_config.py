"""
Tests for configuration loading.
"""

import pytest
import tempfile
from pathlib import Path
import yaml

from hde.config import load_config, load_config_dict, ConfigValidationError


class TestLoadConfigFromFile:
    """Tests for loading config from YAML files."""
    
    def test_load_basic_config(self):
        """Test loading a basic configuration."""
        config_data = {
            "years": 20,
            "discount_rate": 0.03,
            "condo": {
                "monthly_fee": 400,
            },
            "house": {
                "initial_value": 400000,
            },
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name
        
        try:
            condo, house, sim, econ = load_config(config_path)
            
            assert condo.monthly_fee == 400
            assert house.initial_value == 400000
            assert sim.years == 20
            assert sim.discount_rate == 0.03
        finally:
            Path(config_path).unlink()
    
    def test_load_config_with_all_fields(self):
        """Test loading a complete configuration."""
        config_data = {
            "years": 25,
            "discount_rate": 0.035,
            "economic": {
                "mode": "real",
                "inflation_rate": 0.025,
            },
            "condo": {
                "monthly_fee": 550,
                "fee_escalation_rate": 0.02,
                "events": [
                    {
                        "name": "assessment",
                        "base_cost": 5000,
                        "expected_year": 10,
                        "timing_std_years": 2,
                        "cost_vol": 0.20,
                    }
                ],
                "other_recurring_costs": [
                    {
                        "name": "insurance",
                        "annual_amount": 600,
                        "escalation_rate": 0.02,
                    }
                ],
            },
            "house": {
                "initial_value": 500000,
                "value_growth_rate": 0.02,
                "annual_maintenance_rate": 0.015,
                "events": [
                    {
                        "name": "roof",
                        "base_cost": 15000,
                        "expected_year": 20,
                    }
                ],
            },
            "simulation": {
                "num_sims": 5000,
                "random_seed": 123,
                "house_maintenance_vol": 0.25,
                "condo_fee_vol": 0.08,
            },
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name
        
        try:
            condo, house, sim, econ = load_config(config_path)
            
            assert condo.monthly_fee == 550
            assert condo.fee_escalation_rate == 0.02
            assert len(condo.events) == 1
            assert condo.events[0].name == "assessment"
            assert len(condo.other_recurring_costs) == 1
            
            assert house.initial_value == 500000
            assert house.value_growth_rate == 0.02
            assert len(house.events) == 1
            
            assert sim.num_sims == 5000
            assert sim.random_seed == 123
            assert sim.house_maintenance_vol == 0.25
            
            assert econ.mode == "real"
            assert econ.inflation_rate == 0.025
        finally:
            Path(config_path).unlink()
    
    def test_file_not_found(self):
        """Test that FileNotFoundError is raised for missing file."""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")


class TestLoadConfigDict:
    """Tests for loading config from dictionary."""
    
    def test_load_from_dict(self):
        """Test loading configuration from dictionary."""
        config = {
            "years": 20,
            "discount_rate": 0.03,
            "condo": {"monthly_fee": 400},
            "house": {"initial_value": 400000},
        }
        
        condo, house, sim, econ = load_config_dict(config)
        
        assert condo.monthly_fee == 400
        assert house.initial_value == 400000
    
    def test_defaults_applied(self):
        """Test that default values are applied."""
        config = {
            "years": 20,
            "discount_rate": 0.03,
            "condo": {"monthly_fee": 400},
            "house": {"initial_value": 400000},
        }
        
        condo, house, sim, econ = load_config_dict(config)
        
        # Check defaults
        assert condo.fee_escalation_rate == 0.0
        assert house.value_growth_rate == 0.0
        assert house.annual_maintenance_rate == 0.0
        assert sim.num_sims == 10000
        assert sim.random_seed == 42
        assert econ.mode == "real"


class TestValidation:
    """Tests for configuration validation."""
    
    def test_missing_years(self):
        """Test that missing years raises error."""
        config = {
            "discount_rate": 0.03,
            "condo": {"monthly_fee": 400},
            "house": {"initial_value": 400000},
        }
        
        with pytest.raises(ConfigValidationError, match="years"):
            load_config_dict(config)
    
    def test_missing_discount_rate(self):
        """Test that missing discount_rate raises error."""
        config = {
            "years": 20,
            "condo": {"monthly_fee": 400},
            "house": {"initial_value": 400000},
        }
        
        with pytest.raises(ConfigValidationError, match="discount_rate"):
            load_config_dict(config)
    
    def test_missing_condo(self):
        """Test that missing condo section raises error."""
        config = {
            "years": 20,
            "discount_rate": 0.03,
            "house": {"initial_value": 400000},
        }
        
        with pytest.raises(ConfigValidationError, match="condo"):
            load_config_dict(config)
    
    def test_missing_house(self):
        """Test that missing house section raises error."""
        config = {
            "years": 20,
            "discount_rate": 0.03,
            "condo": {"monthly_fee": 400},
        }
        
        with pytest.raises(ConfigValidationError, match="house"):
            load_config_dict(config)
    
    def test_invalid_years(self):
        """Test that invalid years raises error."""
        config = {
            "years": 0,
            "discount_rate": 0.03,
            "condo": {"monthly_fee": 400},
            "house": {"initial_value": 400000},
        }
        
        with pytest.raises(ConfigValidationError, match="years"):
            load_config_dict(config)
    
    def test_negative_discount_rate(self):
        """Test that negative discount_rate raises error."""
        config = {
            "years": 20,
            "discount_rate": -0.01,
            "condo": {"monthly_fee": 400},
            "house": {"initial_value": 400000},
        }
        
        with pytest.raises(ConfigValidationError, match="discount_rate"):
            load_config_dict(config)
    
    def test_invalid_economic_mode(self):
        """Test that invalid economic mode raises error."""
        config = {
            "years": 20,
            "discount_rate": 0.03,
            "economic": {"mode": "invalid"},
            "condo": {"monthly_fee": 400},
            "house": {"initial_value": 400000},
        }
        
        with pytest.raises(ConfigValidationError, match="mode"):
            load_config_dict(config)


class TestEventParsing:
    """Tests for event configuration parsing."""
    
    def test_event_with_all_fields(self):
        """Test parsing event with all fields specified."""
        config = {
            "years": 25,
            "discount_rate": 0.03,
            "condo": {"monthly_fee": 400},
            "house": {
                "initial_value": 400000,
                "events": [
                    {
                        "name": "roof",
                        "base_cost": 15000,
                        "expected_year": 20,
                        "timing_std_years": 3,
                        "min_year": 15,
                        "max_year": 25,
                        "cost_vol": 0.25,
                    }
                ],
            },
        }
        
        _, house, _, _ = load_config_dict(config)
        
        event = house.events[0]
        assert event.name == "roof"
        assert event.base_cost == 15000
        assert event.expected_year == 20
        assert event.timing_std_years == 3
        assert event.min_year == 15
        assert event.max_year == 25
        assert event.cost_vol == 0.25
    
    def test_event_with_defaults(self):
        """Test parsing event with only required fields."""
        config = {
            "years": 25,
            "discount_rate": 0.03,
            "condo": {"monthly_fee": 400},
            "house": {
                "initial_value": 400000,
                "events": [
                    {
                        "name": "roof",
                        "base_cost": 15000,
                        "expected_year": 20,
                    }
                ],
            },
        }
        
        _, house, _, _ = load_config_dict(config)
        
        event = house.events[0]
        assert event.timing_std_years == 0.0
        assert event.min_year == 1
        assert event.max_year is None
        assert event.cost_vol == 0.0
        assert event.timing_model == "jitter"
        assert event.cost_distribution == "lognormal"

    def test_parse_maintenance_curve_and_reserves(self):
        """Test parsing maintenance_curve and reserve fields."""
        config = {
            "years": 20,
            "discount_rate": 0.03,
            "condo": {
                "monthly_fee": 500,
                "reserve_contribution_rate": 0.1,
                "reserve_initial_balance": 1000,
                "reserve_growth_rate": 0.02,
            },
            "house": {
                "initial_value": 300_000,
                "maintenance_curve": [
                    {"year": 1, "rate": 0.01},
                    {"year": 10, "rate": 0.02},
                ],
            },
        }
        
        condo, house, _, _ = load_config_dict(config)
        
        assert condo.reserve_contribution_rate == 0.1
        assert condo.reserve_initial_balance == 1000
        assert condo.reserve_growth_rate == 0.02
        assert house.maintenance_curve == [(1, 0.01), (10, 0.02)]
    
    def test_event_missing_required_field(self):
        """Test that event missing required field raises error."""
        config = {
            "years": 25,
            "discount_rate": 0.03,
            "condo": {"monthly_fee": 400},
            "house": {
                "initial_value": 400000,
                "events": [
                    {
                        "name": "roof",
                        "base_cost": 15000,
                        # missing expected_year
                    }
                ],
            },
        }
        
        with pytest.raises(ConfigValidationError, match="expected_year"):
            load_config_dict(config)


class TestRecurringCostParsing:
    """Tests for recurring other cost parsing."""
    
    def test_recurring_cost_with_all_fields(self):
        """Test parsing recurring cost with all fields."""
        config = {
            "years": 20,
            "discount_rate": 0.03,
            "condo": {
                "monthly_fee": 400,
                "other_recurring_costs": [
                    {
                        "name": "insurance",
                        "annual_amount": 1000,
                        "escalation_rate": 0.02,
                    }
                ],
            },
            "house": {"initial_value": 400000},
        }
        
        condo, _, _, _ = load_config_dict(config)
        
        cost = condo.other_recurring_costs[0]
        assert cost.name == "insurance"
        assert cost.annual_amount == 1000
        assert cost.escalation_rate == 0.02
    
    def test_recurring_cost_with_defaults(self):
        """Test parsing recurring cost with default escalation."""
        config = {
            "years": 20,
            "discount_rate": 0.03,
            "condo": {
                "monthly_fee": 400,
                "other_recurring_costs": [
                    {
                        "name": "insurance",
                        "annual_amount": 1000,
                    }
                ],
            },
            "house": {"initial_value": 400000},
        }
        
        condo, _, _, _ = load_config_dict(config)
        
        cost = condo.other_recurring_costs[0]
        assert cost.escalation_rate == 0.0
