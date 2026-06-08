"""
Tests for deterministic calculations.
"""

import pytest
from hde.models import (
    CondoParams,
    HouseParams,
    SimulationParams,
    EconomicParams,
    EventConfig,
    RecurringOtherCost,
)
from hde.deterministic import compute_deterministic
from hde.pv import pv_annuity, pv_growth_annuity, pv_single


class TestCondoDeterministic:
    """Tests for condo deterministic calculations."""
    
    def test_simple_condo_level_fee(self):
        """Test condo with level (no escalation) fees."""
        condo = CondoParams(monthly_fee=400, fee_escalation_rate=0.0)
        house = HouseParams(initial_value=0, annual_maintenance_rate=0.0)
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        result = compute_deterministic(condo, house, sim, econ)
        
        # Expected: PV of $4800/year for 20 years at 3%
        annual_fee = 400 * 12
        expected = pv_annuity(annual_fee, 0.03, 20)
        
        assert abs(result.condo_pv_base - expected) < 1.0
        assert result.condo_pv_events == 0.0
        assert result.condo_pv_other == 0.0
    
    def test_condo_with_escalation(self):
        """Test condo with fee escalation."""
        condo = CondoParams(monthly_fee=400, fee_escalation_rate=0.02)
        house = HouseParams(initial_value=0, annual_maintenance_rate=0.0)
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        result = compute_deterministic(condo, house, sim, econ)
        
        # With escalation, PV should be higher than level
        annual_fee = 400 * 12
        level_pv = pv_annuity(annual_fee, 0.03, 20)
        
        assert result.condo_pv_base > level_pv
    
    def test_condo_with_event(self):
        """Test condo with a one-time event."""
        event = EventConfig(name="special_assessment", base_cost=5000, expected_year=10)
        condo = CondoParams(monthly_fee=400, events=[event])
        house = HouseParams(initial_value=0)
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        result = compute_deterministic(condo, house, sim, econ)
        
        expected_event_pv = pv_single(5000, 0.03, 10)
        assert abs(result.condo_pv_events - expected_event_pv) < 0.01
    
    def test_condo_with_other_costs(self):
        """Test condo with other recurring costs."""
        other = RecurringOtherCost(name="insurance", annual_amount=1000, escalation_rate=0.0)
        condo = CondoParams(monthly_fee=0, other_recurring_costs=[other])
        house = HouseParams(initial_value=0)
        sim = SimulationParams(years=10, discount_rate=0.05)
        econ = EconomicParams()
        
        result = compute_deterministic(condo, house, sim, econ)
        
        expected_other_pv = pv_annuity(1000, 0.05, 10)
        assert abs(result.condo_pv_other - expected_other_pv) < 0.01
    
    def test_condo_reserves_offset_events(self):
        """Reserve contributions should reduce net event costs."""
        event = EventConfig(name="assessment", base_cost=10_000, expected_year=5)
        condo_no_reserve = CondoParams(monthly_fee=1000, events=[event])
        condo_with_reserve = CondoParams(
            monthly_fee=1000,
            events=[event],
            reserve_contribution_rate=0.5,  # Save half the fee each year
            reserve_growth_rate=0.0,
            reserve_initial_balance=0.0,
        )
        house = HouseParams(initial_value=0)
        sim = SimulationParams(years=6, discount_rate=0.0)
        econ = EconomicParams()
        
        no_reserve_result = compute_deterministic(condo_no_reserve, house, sim, econ)
        reserve_result = compute_deterministic(condo_with_reserve, house, sim, econ)
        
        # With a 0% discount rate, reserve contributions (5 years * $6k) cover the $10k assessment.
        assert reserve_result.condo_pv_events < no_reserve_result.condo_pv_events


class TestHouseDeterministic:
    """Tests for house deterministic calculations."""
    
    def test_simple_house_maintenance(self):
        """Test house with level maintenance (no value growth)."""
        condo = CondoParams(monthly_fee=0)
        house = HouseParams(
            initial_value=400_000,
            value_growth_rate=0.0,
            annual_maintenance_rate=0.015,
        )
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        result = compute_deterministic(condo, house, sim, econ)
        
        # Expected: PV of $6000/year (0.015 * 400k) for 20 years at 3%
        annual_maint = 0.015 * 400_000
        expected = pv_annuity(annual_maint, 0.03, 20)
        
        assert abs(result.house_pv_base - expected) < 1.0
    
    def test_house_with_value_growth(self):
        """Test house with growing value (growing maintenance)."""
        condo = CondoParams(monthly_fee=0)
        house = HouseParams(
            initial_value=400_000,
            value_growth_rate=0.02,
            annual_maintenance_rate=0.015,
        )
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        result = compute_deterministic(condo, house, sim, econ)
        
        # With value growth, maintenance PV should be higher
        annual_maint = 0.015 * 400_000
        level_pv = pv_annuity(annual_maint, 0.03, 20)
        
        assert result.house_pv_base > level_pv
    
    def test_house_with_events(self):
        """Test house with multiple events."""
        events = [
            EventConfig(name="roof", base_cost=12000, expected_year=15),
            EventConfig(name="hvac", base_cost=7000, expected_year=10),
        ]
        condo = CondoParams(monthly_fee=0)
        house = HouseParams(initial_value=0, events=events)
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        result = compute_deterministic(condo, house, sim, econ)
        
        expected = pv_single(12000, 0.03, 15) + pv_single(7000, 0.03, 10)
        assert abs(result.house_pv_events - expected) < 0.01
    
    def test_house_maintenance_curve(self):
        """Maintenance should follow an age/condition curve."""
        condo = CondoParams(monthly_fee=0)
        house = HouseParams(
            initial_value=100_000,
            value_growth_rate=0.0,
            annual_maintenance_rate=0.01,
            maintenance_curve=[(1, 0.01), (10, 0.02)],
        )
        sim = SimulationParams(years=10, discount_rate=0.0)
        econ = EconomicParams()
        
        result = compute_deterministic(condo, house, sim, econ)
        
        # Curve rises from 1% to 2%, so PV should exceed flat 1% maintenance.
        flat_maint = pv_annuity(0.01 * 100_000, 0.0, 10)
        assert result.house_pv_base > flat_maint


class TestDiffCalculation:
    """Tests for difference calculation."""
    
    def test_diff_positive_house_more_expensive(self):
        """Test that positive diff means house is more expensive."""
        condo = CondoParams(monthly_fee=100)  # Low fees
        house = HouseParams(initial_value=500_000, annual_maintenance_rate=0.02)  # High maintenance
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        result = compute_deterministic(condo, house, sim, econ)
        
        assert result.diff_pv > 0
        assert result.diff_pv == result.house_pv_total - result.condo_pv_total
    
    def test_diff_negative_condo_more_expensive(self):
        """Test that negative diff means condo is more expensive."""
        condo = CondoParams(monthly_fee=1000)  # High fees
        house = HouseParams(initial_value=100_000, annual_maintenance_rate=0.005)  # Low maintenance
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        result = compute_deterministic(condo, house, sim, econ)
        
        assert result.diff_pv < 0
    
    def test_totals_sum_correctly(self):
        """Test that total equals sum of components."""
        event = EventConfig(name="roof", base_cost=10000, expected_year=10)
        other = RecurringOtherCost(name="insurance", annual_amount=1000)
        
        condo = CondoParams(monthly_fee=400, events=[event], other_recurring_costs=[other])
        house = HouseParams(
            initial_value=400_000,
            annual_maintenance_rate=0.015,
            events=[event],
            other_recurring_costs=[other],
        )
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        result = compute_deterministic(condo, house, sim, econ)
        
        condo_sum = result.condo_pv_base + result.condo_pv_events + result.condo_pv_other
        house_sum = result.house_pv_base + result.house_pv_events + result.house_pv_other
        
        assert abs(result.condo_pv_total - condo_sum) < 0.01
        assert abs(result.house_pv_total - house_sum) < 0.01


class TestEventYearClamping:
    """Tests for event year clamping behavior."""
    
    def test_event_year_clamped_to_horizon(self):
        """Test that events beyond horizon are clamped."""
        event = EventConfig(name="far_future", base_cost=10000, expected_year=50)
        condo = CondoParams(monthly_fee=0)
        house = HouseParams(initial_value=0, events=[event])
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        result = compute_deterministic(condo, house, sim, econ)
        
        # Event should be clamped to year 20
        expected = pv_single(10000, 0.03, 20)
        assert abs(result.house_pv_events - expected) < 0.01
    
    def test_event_year_zero_clamped_to_one(self):
        """Test that events at year 0 are clamped to year 1."""
        event = EventConfig(name="immediate", base_cost=10000, expected_year=0)
        condo = CondoParams(monthly_fee=0)
        house = HouseParams(initial_value=0, events=[event])
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        result = compute_deterministic(condo, house, sim, econ)
        
        # Event should be clamped to year 1
        expected = pv_single(10000, 0.03, 1)
        assert abs(result.house_pv_events - expected) < 0.01
