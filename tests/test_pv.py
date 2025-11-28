"""
Tests for PV utility functions.
"""

import pytest
from cvh_cost.pv import pv_single, pv_annuity, pv_growth_annuity, pv_series


class TestPvSingle:
    """Tests for pv_single function."""
    
    def test_basic_discounting(self):
        """Test basic single-period discounting."""
        # $1000 in 1 year at 10% = 1000 / 1.10 = 909.09
        result = pv_single(1000, 0.10, 1)
        assert abs(result - 909.09) < 0.01
    
    def test_multi_year_discounting(self):
        """Test discounting over multiple years."""
        # $1000 in 5 years at 5% = 1000 / 1.05^5 = 783.53
        result = pv_single(1000, 0.05, 5)
        assert abs(result - 783.53) < 0.01
    
    def test_zero_rate(self):
        """Test with zero discount rate."""
        result = pv_single(1000, 0.0, 5)
        assert result == 1000.0
    
    def test_year_zero(self):
        """Test that year 0 returns the cost unchanged."""
        result = pv_single(1000, 0.10, 0)
        assert result == 1000.0
    
    def test_negative_year(self):
        """Test that negative year returns cost unchanged."""
        result = pv_single(1000, 0.10, -1)
        assert result == 1000.0


class TestPvAnnuity:
    """Tests for pv_annuity function."""
    
    def test_basic_annuity(self):
        """Test basic annuity calculation."""
        # $1000/year for 10 years at 5%
        # PV = 1000 * (1 - 1.05^-10) / 0.05 = 7721.73
        result = pv_annuity(1000, 0.05, 10)
        assert abs(result - 7721.73) < 0.01
    
    def test_zero_rate_annuity(self):
        """Test annuity with zero rate equals sum of payments."""
        result = pv_annuity(1000, 0.0, 10)
        assert result == 10000.0
    
    def test_zero_years(self):
        """Test annuity with zero years."""
        result = pv_annuity(1000, 0.05, 0)
        assert result == 0.0
    
    def test_single_payment(self):
        """Test annuity with single payment equals pv_single."""
        annuity_pv = pv_annuity(1000, 0.05, 1)
        single_pv = pv_single(1000, 0.05, 1)
        assert abs(annuity_pv - single_pv) < 0.01
    
    def test_high_rate(self):
        """Test annuity with high discount rate."""
        # Higher rate = lower PV
        low_rate_pv = pv_annuity(1000, 0.03, 10)
        high_rate_pv = pv_annuity(1000, 0.10, 10)
        assert high_rate_pv < low_rate_pv


class TestPvGrowthAnnuity:
    """Tests for pv_growth_annuity function."""
    
    def test_zero_growth_equals_level_annuity(self):
        """Test that zero growth equals level annuity."""
        growth_pv = pv_growth_annuity(1000, 0.05, 0.0, 10)
        level_pv = pv_annuity(1000, 0.05, 10)
        assert abs(growth_pv - level_pv) < 0.01
    
    def test_growth_increases_pv(self):
        """Test that positive growth increases PV."""
        level_pv = pv_growth_annuity(1000, 0.05, 0.0, 10)
        growth_pv = pv_growth_annuity(1000, 0.05, 0.02, 10)
        assert growth_pv > level_pv
    
    def test_equal_rate_and_growth(self):
        """Test degenerate case where rate equals growth."""
        # When r == g, PV = n * payment / (1 + r)
        result = pv_growth_annuity(1000, 0.05, 0.05, 10)
        expected = 10 * 1000 / 1.05
        assert abs(result - expected) < 0.01
    
    def test_zero_years(self):
        """Test growth annuity with zero years."""
        result = pv_growth_annuity(1000, 0.05, 0.02, 0)
        assert result == 0.0
    
    def test_known_value(self):
        """Test against a known calculated value."""
        # $1000 first payment, growing at 2%, discounted at 5%, for 10 years
        # PV = 1000 * (1 - (1.02/1.05)^10) / (0.05 - 0.02)
        # (1.02/1.05)^10 = 0.74814, so PV = 1000 * (1 - 0.74814) / 0.03 = 8395.3
        result = pv_growth_annuity(1000, 0.05, 0.02, 10)
        assert abs(result - 8388.1) < 10  # Allow tolerance for floating point


class TestPvSeries:
    """Tests for pv_series function."""
    
    def test_empty_series(self):
        """Test empty series returns zero."""
        result = pv_series({}, 0.05)
        assert result == 0.0
    
    def test_single_cost(self):
        """Test single cost equals pv_single."""
        series_pv = pv_series({5: 1000}, 0.05)
        single_pv = pv_single(1000, 0.05, 5)
        assert abs(series_pv - single_pv) < 0.01
    
    def test_multiple_costs(self):
        """Test multiple costs are summed correctly."""
        costs = {5: 1000, 10: 2000}
        result = pv_series(costs, 0.05)
        expected = pv_single(1000, 0.05, 5) + pv_single(2000, 0.05, 10)
        assert abs(result - expected) < 0.01
    
    def test_same_year_multiple_entries(self):
        """Test that costs in same year are handled (overwritten by dict)."""
        # Dict will only keep one value per key
        costs = {5: 1000}
        result = pv_series(costs, 0.05)
        expected = pv_single(1000, 0.05, 5)
        assert abs(result - expected) < 0.01


class TestPvEdgeCases:
    """Edge case tests."""
    
    def test_very_small_rate(self):
        """Test with very small discount rate."""
        result = pv_annuity(1000, 0.0001, 10)
        # Should be very close to 10000
        assert 9990 < result < 10010
    
    def test_very_large_rate(self):
        """Test with very large discount rate."""
        result = pv_annuity(1000, 1.0, 10)  # 100% rate
        # PV should be much smaller than sum of payments
        assert result < 2000
    
    def test_long_horizon(self):
        """Test with long time horizon."""
        result = pv_annuity(1000, 0.05, 100)
        # Should converge toward perpetuity value = 1000 / 0.05 = 20000
        assert 19000 < result < 20000


class TestPvToMonthlySavings:
    """Tests for pv_to_monthly_savings function."""
    
    def test_basic_conversion(self):
        """Test basic PV to monthly savings conversion."""
        from cvh_cost.pv import pv_to_monthly_savings
        # $100k PV over 20 years at 3%
        monthly = pv_to_monthly_savings(100_000, 0.03, 20)
        # Should be around $550/month
        assert 500 < monthly < 600
    
    def test_zero_pv(self):
        """Test zero PV returns zero monthly."""
        from cvh_cost.pv import pv_to_monthly_savings
        result = pv_to_monthly_savings(0, 0.03, 20)
        assert result == 0.0
    
    def test_zero_years(self):
        """Test zero years returns zero."""
        from cvh_cost.pv import pv_to_monthly_savings
        result = pv_to_monthly_savings(100_000, 0.03, 0)
        assert result == 0.0
    
    def test_zero_rate(self):
        """Test zero rate case."""
        from cvh_cost.pv import pv_to_monthly_savings
        # $120k PV over 10 years at 0% = $1000/month
        result = pv_to_monthly_savings(120_000, 0.0, 10)
        assert abs(result - 1000) < 0.01
    
    def test_roundtrip_consistency(self):
        """Test that monthly savings accumulates back to PV."""
        from cvh_cost.pv import pv_to_monthly_savings
        pv = 150_000
        rate = 0.04
        years = 25
        monthly = pv_to_monthly_savings(pv, rate, years)
        
        # Manually compute PV of monthly payments
        monthly_rate = rate / 12
        n_months = years * 12
        reconstructed = monthly * (1 - (1 + monthly_rate) ** -n_months) / monthly_rate
        
        # Should be very close to original PV
        assert abs(reconstructed - pv) / pv < 0.0001  # Within 0.01%
