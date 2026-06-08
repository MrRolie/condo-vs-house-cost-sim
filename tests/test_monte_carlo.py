"""
Tests for Monte Carlo simulation.
"""

import pytest
import numpy as np
from hde.models import (
    CondoParams,
    HouseParams,
    SimulationParams,
    EconomicParams,
    EventConfig,
    RecurringOtherCost,
    ComparisonSpec,
)
from hde.deterministic import compute_deterministic
from hde.monte_carlo import run_monte_carlo


def _ch_spec(condo, house, sim, econ):
    """Wrap a condo/house pair into a ComparisonSpec (migration helper)."""
    return ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house)


class TestMonteCarloBasics:
    """Basic Monte Carlo tests."""
    
    def test_output_shapes(self):
        """Test that output arrays have correct shapes."""
        condo = CondoParams(monthly_fee=400)
        house = HouseParams(initial_value=400_000, annual_maintenance_rate=0.015)
        sim = SimulationParams(years=20, discount_rate=0.03, num_sims=1000)
        econ = EconomicParams()
        
        result = run_monte_carlo(_ch_spec(condo, house, sim, econ))

        assert result.condo.pvs.shape == (1000,)
        assert result.house.pvs.shape == (1000,)
        assert (result.house.pvs - result.condo.pvs).shape == (1000,)
    
    def test_reproducibility_with_seed(self):
        """Test that same seed produces same results."""
        condo = CondoParams(monthly_fee=400)
        house = HouseParams(initial_value=400_000, annual_maintenance_rate=0.015)
        sim = SimulationParams(years=20, discount_rate=0.03, num_sims=100, random_seed=42)
        econ = EconomicParams()
        
        result1 = run_monte_carlo(_ch_spec(condo, house, sim, econ))
        result2 = run_monte_carlo(_ch_spec(condo, house, sim, econ))

        np.testing.assert_array_equal(result1.condo.pvs, result2.condo.pvs)
        np.testing.assert_array_equal(result1.house.pvs, result2.house.pvs)
    
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
        
        result1 = run_monte_carlo(_ch_spec(condo, house, sim1, econ))
        result2 = run_monte_carlo(_ch_spec(condo, house, sim2, econ))

        assert not np.array_equal(result1.condo.pvs, result2.condo.pvs)


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
        
        spec = _ch_spec(condo, house, sim, econ)
        det_result = compute_deterministic(spec)
        mc_result = run_monte_carlo(spec)

        # With zero volatility (and no events), MC should exactly equal deterministic
        # All simulations should be identical
        assert abs(mc_result.condo.summary.mean - det_result.condo.total_pv) < 1.0
        assert abs(mc_result.house.summary.mean - det_result.house.total_pv) < 1.0
        assert mc_result.condo.summary.std < 1.0  # Should be essentially zero
        assert mc_result.house.summary.std < 1.0


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
        
        result_low = run_monte_carlo(_ch_spec(condo, house, sim_low, econ))
        result_high = run_monte_carlo(_ch_spec(condo, house, sim_high, econ))

        assert result_high.house.summary.std > result_low.house.summary.std
    
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
        
        result_low = run_monte_carlo(_ch_spec(condo, house, sim_low, econ))
        result_high = run_monte_carlo(_ch_spec(condo, house, sim_high, econ))

        spread_low = result_low.house.summary.p95 - result_low.house.summary.p5
        spread_high = result_high.house.summary.p95 - result_high.house.summary.p5
        
        assert spread_high > spread_low


class TestMonteCarloProbability:
    """Test probability calculations."""
    
    def test_prob_in_valid_range(self):
        """Test that probability is between 0 and 1."""
        condo = CondoParams(monthly_fee=400)
        house = HouseParams(initial_value=400_000, annual_maintenance_rate=0.015)
        sim = SimulationParams(years=20, discount_rate=0.03, num_sims=1000)
        econ = EconomicParams()
        
        result = run_monte_carlo(_ch_spec(condo, house, sim, econ))

        assert 0.0 <= result.prob_condo_cheapest <= 1.0
    
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
        
        result = run_monte_carlo(_ch_spec(condo, house, sim, econ))

        # With similar costs and volatility, probability should be around 50%
        # Allow wide tolerance due to randomness
        assert abs(result.prob_condo_cheapest - 0.5) < 0.15
    
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
        
        result = run_monte_carlo(_ch_spec(condo, house, sim, econ))

        # House is clearly more expensive -> condo is cheapest almost always
        assert result.prob_condo_cheapest > 0.90


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
        
        result = run_monte_carlo(_ch_spec(condo, house, sim, econ))

        # Check house summary matches array
        assert abs(result.house.summary.mean - np.mean(result.house.pvs)) < 0.01
        assert abs(result.house.summary.std - np.std(result.house.pvs)) < 0.01
        assert abs(result.house.summary.p50 - np.median(result.house.pvs)) < 0.01
    
    def test_percentiles_ordered(self):
        """Test that percentiles are properly ordered."""
        condo = CondoParams(monthly_fee=400)
        house = HouseParams(initial_value=400_000, annual_maintenance_rate=0.015)
        sim = SimulationParams(
            years=20, discount_rate=0.03, num_sims=1000,
            house_maintenance_vol=0.20,
        )
        econ = EconomicParams()
        
        result = run_monte_carlo(_ch_spec(condo, house, sim, econ))

        assert result.house.summary.p5 <= result.house.summary.p50 <= result.house.summary.p95


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
        result = run_monte_carlo(_ch_spec(condo, house, sim, econ))

        # All PVs should be positive (event cost is positive)
        assert np.all(result.house.pvs > 0)
    
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
        
        result = run_monte_carlo(_ch_spec(condo, house, sim, econ))

        # All PVs should be identical
        assert result.house.summary.std < 0.01


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
        
        low = run_monte_carlo(_ch_spec(condo, house, sim_low, econ))
        high = run_monte_carlo(_ch_spec(condo, house, sim_high, econ))

        assert high.condo.summary.std > low.condo.summary.std
    
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
        
        result = run_monte_carlo(_ch_spec(condo, house, sim, econ))

        # With zero hazard, events never fire so PV should be ~0
        assert result.house.summary.mean < 1.0
    
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
        
        no_reserve = run_monte_carlo(_ch_spec(condo_no_reserve, house, sim, econ))
        with_reserve = run_monte_carlo(_ch_spec(condo_with_reserve, house, sim, econ))

        assert with_reserve.condo.summary.mean < no_reserve.condo.summary.mean


from hde.models import (
    ComparisonSpec, RentParams, IncomeParams, PayDropEvent,
    ComparisonMonteCarloResult, CondoParams, HouseParams,
    SimulationParams, EconomicParams,
)


def _spec(condo=None, house=None, rent=None, income=None, years=10, dr=0.05, num_sims=500, seed=42):
    return ComparisonSpec(
        simulation=SimulationParams(years=years, discount_rate=dr, num_sims=num_sims, random_seed=seed),
        economic=EconomicParams(),
        condo=condo, house=house, rent=rent, income=income,
    )


class TestRentMC:
    def test_rent_mc_output_shape(self):
        rent = RentParams(monthly_rent=2000.0, rent_escalation_rate=0.02)
        spec = _spec(rent=rent, num_sims=200)
        result = run_monte_carlo(spec)
        assert result.rent is not None
        assert result.rent.pvs.shape == (200,)

    def test_rent_mc_zero_vol_converges_to_deterministic(self):
        """With zero vol, MC mean ≈ deterministic PV (within 1%)."""
        from hde.deterministic import compute_deterministic
        rent = RentParams(monthly_rent=2000.0, rent_escalation_rate=0.0, invested_down_payment=0.0)
        spec = _spec(rent=rent, num_sims=1000)
        mc = run_monte_carlo(spec)
        det = compute_deterministic(spec)
        assert abs(mc.rent.summary.mean - det.rent.total_pv) / det.rent.total_pv < 0.01

    def test_rent_mc_zero_vol_nominal_mode_matches_deterministic(self):
        """Nominal-mode escalation parity: MC rent folds in inflation like the
        deterministic model, so zero-vol MC mean still tracks deterministic PV."""
        from hde.deterministic import compute_deterministic
        rent = RentParams(monthly_rent=2000.0, rent_escalation_rate=0.02, invested_down_payment=0.0)
        spec = ComparisonSpec(
            simulation=SimulationParams(years=10, discount_rate=0.05, num_sims=1000, random_seed=42),
            economic=EconomicParams(mode="nominal", inflation_rate=0.03),
            rent=rent,
        )
        mc = run_monte_carlo(spec)
        det = compute_deterministic(spec)
        assert abs(mc.rent.summary.mean - det.rent.total_pv) / det.rent.total_pv < 0.01


class TestRankingProbs:
    def test_prob_cheapest_sums_to_one(self):
        """All three options: ranking probs sum to 1.0."""
        condo = CondoParams(monthly_fee=800.0)
        house = HouseParams(initial_value=400_000.0, value_growth_rate=0.0, annual_maintenance_rate=0.01)
        rent = RentParams(monthly_rent=2000.0)
        spec = _spec(condo=condo, house=house, rent=rent, num_sims=500)
        result = run_monte_carlo(spec)
        assert result.prob_rent_cheapest is not None
        assert result.prob_condo_cheapest is not None
        assert result.prob_house_cheapest is not None
        total = result.prob_rent_cheapest + result.prob_condo_cheapest + result.prob_house_cheapest
        assert abs(total - 1.0) < 1e-9

    def test_prob_cheapest_none_when_single_option(self):
        rent = RentParams(monthly_rent=2000.0)
        spec = _spec(rent=rent, num_sims=100)
        result = run_monte_carlo(spec)
        assert result.prob_rent_cheapest is None
        assert result.prob_condo_cheapest is None
        assert result.prob_house_cheapest is None

    def test_prob_cheapest_two_options_sums_to_one(self):
        condo = CondoParams(monthly_fee=600.0)
        house = HouseParams(initial_value=400_000.0, value_growth_rate=0.0, annual_maintenance_rate=0.015)
        spec = _spec(condo=condo, house=house, num_sims=500)
        result = run_monte_carlo(spec)
        assert 0.0 <= result.prob_condo_cheapest <= 1.0
        assert 0.0 <= result.prob_house_cheapest <= 1.0
        assert abs(result.prob_condo_cheapest + result.prob_house_cheapest - 1.0) < 1e-9
        assert result.prob_rent_cheapest is None


class TestAffordabilityMC:
    def test_affordability_mc_prob_in_valid_range(self):
        income = IncomeParams(annual_income=50_000.0, affordability_threshold=0.35)
        condo = CondoParams(monthly_fee=1000.0)  # 12k/50k=24%, below threshold
        spec = _spec(condo=condo, income=income, num_sims=200)
        result = run_monte_carlo(spec)
        assert result.affordability_mc is not None
        assert 0.0 <= result.affordability_mc.prob_condo_exceeds <= 1.0

    def test_no_income_no_affordability_mc(self):
        condo = CondoParams(monthly_fee=500.0)
        spec = _spec(condo=condo, num_sims=100)
        result = run_monte_carlo(spec)
        assert result.affordability_mc is None
