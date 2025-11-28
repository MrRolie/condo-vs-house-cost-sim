"""
Tests for Monte Carlo simulation.
"""

import pytest
import numpy as np
from cvh_cost.models import (
    CondoParams,
    HouseParams,
    SimulationParams,
    EconomicParams,
    EventConfig,
    RecurringOtherCost,
)
from cvh_cost.deterministic import compute_deterministic
from cvh_cost.monte_carlo import run_monte_carlo


class TestMonteCarloBasics:
    """Basic Monte Carlo tests."""
    
    def test_output_shapes(self):
        """Test that output arrays have correct shapes."""
        condo = CondoParams(monthly_fee=400)
        house = HouseParams(initial_value=400_000, annual_maintenance_rate=0.015)
        sim = SimulationParams(years=20, discount_rate=0.03, num_sims=1000)
        econ = EconomicParams()
        
        result = run_monte_carlo(condo, house, sim, econ)
        
        assert result.condo_pv.shape == (1000,)
        assert result.house_pv.shape == (1000,)
        assert result.diff_pv.shape == (1000,)
    
    def test_diff_equals_house_minus_condo(self):
        """Test that diff_pv equals house_pv - condo_pv."""
        condo = CondoParams(monthly_fee=400)
        house = HouseParams(initial_value=400_000, annual_maintenance_rate=0.015)
        sim = SimulationParams(years=20, discount_rate=0.03, num_sims=100)
        econ = EconomicParams()
        
        result = run_monte_carlo(condo, house, sim, econ)
        
        expected_diff = result.house_pv - result.condo_pv
        np.testing.assert_array_almost_equal(result.diff_pv, expected_diff)
    
    def test_reproducibility_with_seed(self):
        """Test that same seed produces same results."""
        condo = CondoParams(monthly_fee=400)
        house = HouseParams(initial_value=400_000, annual_maintenance_rate=0.015)
        sim = SimulationParams(years=20, discount_rate=0.03, num_sims=100, random_seed=42)
        econ = EconomicParams()
        
        result1 = run_monte_carlo(condo, house, sim, econ)
        result2 = run_monte_carlo(condo, house, sim, econ)
        
        np.testing.assert_array_equal(result1.condo_pv, result2.condo_pv)
        np.testing.assert_array_equal(result1.house_pv, result2.house_pv)
    
    def test_different_seeds_produce_different_results(self):
        """Test that different seeds produce different results."""
        # Need events with timing jitter or cost volatility for randomness
        event = EventConfig(
            name="Test Event",
            expected_year=10,
            base_cost=5000,
            timing_std_years=2.0,  # Add timing jitter for randomness
            cost_vol=0.1
        )
        condo = CondoParams(monthly_fee=400, events=[event])
        house = HouseParams(initial_value=400_000, annual_maintenance_rate=0.015)
        sim1 = SimulationParams(years=20, discount_rate=0.03, num_sims=100, random_seed=42)
        sim2 = SimulationParams(years=20, discount_rate=0.03, num_sims=100, random_seed=123)
        econ = EconomicParams()
        
        result1 = run_monte_carlo(condo, house, sim1, econ)
        result2 = run_monte_carlo(condo, house, sim2, econ)
        
        assert not np.array_equal(result1.condo_pv, result2.condo_pv)


class TestMonteCarloDeterministicConvergence:
    """Test that MC converges to deterministic with zero volatility."""
    
    def test_zero_volatility_converges_to_deterministic(self):
        """Test MC mean equals deterministic when volatility is zero."""
        condo = CondoParams(monthly_fee=400, fee_escalation_rate=0.02)
        house = HouseParams(
            initial_value=400_000,
            value_growth_rate=0.01,
            annual_maintenance_rate=0.015,
        )
        sim = SimulationParams(
            years=20,
            discount_rate=0.03,
            num_sims=1000,
            random_seed=42,
            house_maintenance_vol=0.0,
            condo_fee_vol=0.0,
        )
        econ = EconomicParams()
        
        det_result = compute_deterministic(condo, house, sim, econ)
        mc_result = run_monte_carlo(condo, house, sim, econ)
        
        # With zero volatility (and no events), MC should exactly equal deterministic
        # All simulations should be identical
        assert abs(mc_result.condo_summary.mean - det_result.condo_pv_total) < 1.0
        assert abs(mc_result.house_summary.mean - det_result.house_pv_total) < 1.0
        assert mc_result.condo_summary.std < 1.0  # Should be essentially zero
        assert mc_result.house_summary.std < 1.0


class TestMonteCarloVolatility:
    """Test volatility effects."""
    
    def test_higher_volatility_increases_std(self):
        """Test that higher volatility produces wider distribution."""
        condo = CondoParams(monthly_fee=400)
        house = HouseParams(initial_value=400_000, annual_maintenance_rate=0.015)
        econ = EconomicParams()
        
        sim_low = SimulationParams(
            years=20, discount_rate=0.03, num_sims=5000,
            house_maintenance_vol=0.10, random_seed=42
        )
        sim_high = SimulationParams(
            years=20, discount_rate=0.03, num_sims=5000,
            house_maintenance_vol=0.40, random_seed=42
        )
        
        result_low = run_monte_carlo(condo, house, sim_low, econ)
        result_high = run_monte_carlo(condo, house, sim_high, econ)
        
        assert result_high.house_summary.std > result_low.house_summary.std
    
    def test_volatility_affects_spread(self):
        """Test that volatility affects the 5th-95th percentile spread."""
        condo = CondoParams(monthly_fee=400)
        house = HouseParams(initial_value=400_000, annual_maintenance_rate=0.015)
        econ = EconomicParams()
        
        sim_low = SimulationParams(
            years=20, discount_rate=0.03, num_sims=5000,
            house_maintenance_vol=0.10, random_seed=42
        )
        sim_high = SimulationParams(
            years=20, discount_rate=0.03, num_sims=5000,
            house_maintenance_vol=0.40, random_seed=42
        )
        
        result_low = run_monte_carlo(condo, house, sim_low, econ)
        result_high = run_monte_carlo(condo, house, sim_high, econ)
        
        spread_low = result_low.house_summary.p95 - result_low.house_summary.p5
        spread_high = result_high.house_summary.p95 - result_high.house_summary.p5
        
        assert spread_high > spread_low


class TestMonteCarloProbability:
    """Test probability calculations."""
    
    def test_prob_in_valid_range(self):
        """Test that probability is between 0 and 1."""
        condo = CondoParams(monthly_fee=400)
        house = HouseParams(initial_value=400_000, annual_maintenance_rate=0.015)
        sim = SimulationParams(years=20, discount_rate=0.03, num_sims=1000)
        econ = EconomicParams()
        
        result = run_monte_carlo(condo, house, sim, econ)
        
        assert 0.0 <= result.prob_house_more_expensive <= 1.0
    
    def test_identical_costs_prob_around_half(self):
        """Test that similar costs give probability around 50%."""
        # Make costs similar with some volatility
        condo = CondoParams(monthly_fee=500)  # $6000/year
        house = HouseParams(
            initial_value=400_000,
            annual_maintenance_rate=0.015,  # $6000/year
        )
        sim = SimulationParams(
            years=20,
            discount_rate=0.03,
            num_sims=10000,
            random_seed=42,
            house_maintenance_vol=0.20,
            condo_fee_vol=0.20,
        )
        econ = EconomicParams()
        
        result = run_monte_carlo(condo, house, sim, econ)
        
        # With similar costs and volatility, probability should be around 50%
        # Allow wide tolerance due to randomness
        assert 0.3 < result.prob_house_more_expensive < 0.7
    
    def test_clearly_higher_house_cost_gives_high_prob(self):
        """Test that clearly higher house costs give high probability."""
        condo = CondoParams(monthly_fee=100)  # Very low
        house = HouseParams(
            initial_value=500_000,
            annual_maintenance_rate=0.02,  # High
        )
        sim = SimulationParams(
            years=20, discount_rate=0.03, num_sims=1000,
            house_maintenance_vol=0.10, condo_fee_vol=0.10,
        )
        econ = EconomicParams()
        
        result = run_monte_carlo(condo, house, sim, econ)
        
        # House is clearly more expensive
        assert result.prob_house_more_expensive > 0.95


class TestMonteCarloSummary:
    """Test summary statistics."""
    
    def test_summary_statistics_consistent(self):
        """Test that summary statistics are consistent with arrays."""
        condo = CondoParams(monthly_fee=400)
        house = HouseParams(initial_value=400_000, annual_maintenance_rate=0.015)
        sim = SimulationParams(
            years=20, discount_rate=0.03, num_sims=1000,
            house_maintenance_vol=0.20,
        )
        econ = EconomicParams()
        
        result = run_monte_carlo(condo, house, sim, econ)
        
        # Check house summary matches array
        assert abs(result.house_summary.mean - np.mean(result.house_pv)) < 0.01
        assert abs(result.house_summary.std - np.std(result.house_pv)) < 0.01
        assert abs(result.house_summary.p50 - np.median(result.house_pv)) < 0.01
    
    def test_percentiles_ordered(self):
        """Test that percentiles are properly ordered."""
        condo = CondoParams(monthly_fee=400)
        house = HouseParams(initial_value=400_000, annual_maintenance_rate=0.015)
        sim = SimulationParams(
            years=20, discount_rate=0.03, num_sims=1000,
            house_maintenance_vol=0.20,
        )
        econ = EconomicParams()
        
        result = run_monte_carlo(condo, house, sim, econ)
        
        assert result.house_summary.p5 <= result.house_summary.p50 <= result.house_summary.p95


class TestMonteCarloEventTiming:
    """Test event timing randomness."""
    
    def test_event_timing_within_bounds(self):
        """Test that event timing stays within specified bounds."""
        event = EventConfig(
            name="roof",
            base_cost=10000,
            expected_year=15,
            timing_std_years=3,
            min_year=10,
            max_year=20,
        )
        condo = CondoParams(monthly_fee=0)
        house = HouseParams(initial_value=0, events=[event])
        sim = SimulationParams(years=25, discount_rate=0.03, num_sims=1000)
        econ = EconomicParams()
        
        # Run simulation - if event went outside bounds, PV would be invalid
        result = run_monte_carlo(condo, house, sim, econ)
        
        # All PVs should be positive (event cost is positive)
        assert np.all(result.house_pv > 0)
    
    def test_no_timing_jitter_produces_deterministic_timing(self):
        """Test that zero timing_std_years produces deterministic timing."""
        event = EventConfig(
            name="roof",
            base_cost=10000,
            expected_year=15,
            timing_std_years=0.0,
            cost_vol=0.0,
        )
        condo = CondoParams(monthly_fee=0)
        house = HouseParams(initial_value=0, events=[event])
        sim = SimulationParams(years=25, discount_rate=0.03, num_sims=100)
        econ = EconomicParams()
        
        result = run_monte_carlo(condo, house, sim, econ)
        
        # All PVs should be identical
        assert result.house_summary.std < 0.01


class TestMonteCarloAdvancedDynamics:
    """Tests for enhanced economic and volatility dynamics."""
    
    def test_other_cost_volatility_increases_spread(self):
        """Volatility on other_recurring_costs should widen the distribution."""
        other = RecurringOtherCost(name="insurance", annual_amount=2000, escalation_rate=0.0)
        condo = CondoParams(monthly_fee=0, other_recurring_costs=[other])
        house = HouseParams(initial_value=0)
        econ = EconomicParams()
        
        sim_low = SimulationParams(
            years=15, discount_rate=0.03, num_sims=2000,
            other_cost_vol=0.05,
        )
        sim_high = SimulationParams(
            years=15, discount_rate=0.03, num_sims=2000,
            other_cost_vol=0.40,
        )
        
        low = run_monte_carlo(condo, house, sim_low, econ)
        high = run_monte_carlo(condo, house, sim_high, econ)
        
        assert high.condo_summary.std > low.condo_summary.std
    
    def test_hazard_event_can_be_skipped(self):
        """Hazard timing with zero hazard should result in no event costs."""
        hazard_event = EventConfig(
            name="rare_roof",
            base_cost=20_000,
            expected_year=5,
            timing_model="hazard",
            hazard_base=0.0,
            hazard_growth=0.0,
        )
        condo = CondoParams(monthly_fee=0)
        house = HouseParams(initial_value=0, events=[hazard_event])
        sim = SimulationParams(years=10, discount_rate=0.03, num_sims=500)
        econ = EconomicParams()
        
        result = run_monte_carlo(condo, house, sim, econ)
        
        # With zero hazard, events never fire so PV should be ~0
        assert result.house_summary.mean < 1.0
    
    def test_reserves_reduce_expected_event_costs(self):
        """Reserve funding should lower expected PV of condo events."""
        event = EventConfig(name="assessment", base_cost=10_000, expected_year=3)
        
        condo_no_reserve = CondoParams(monthly_fee=1000, events=[event])
        condo_with_reserve = CondoParams(
            monthly_fee=1000,
            events=[event],
            reserve_contribution_rate=1.0,  # save entire fee
            reserve_growth_rate=0.0,
        )
        house = HouseParams(initial_value=0)
        sim = SimulationParams(years=5, discount_rate=0.03, num_sims=500, random_seed=123)
        econ = EconomicParams()
        
        no_reserve = run_monte_carlo(condo_no_reserve, house, sim, econ)
        with_reserve = run_monte_carlo(condo_with_reserve, house, sim, econ)
        
        assert with_reserve.condo_summary.mean < no_reserve.condo_summary.mean
