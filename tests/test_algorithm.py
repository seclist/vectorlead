"""Unit tests for Account Health Score (AHS) mathematical engine."""

import pytest
from src.algorithm import (
    AccountMetrics,
    AHSResult,
    calculate_ahs,
    calculate_dynamic_multiplier,
    clamp,
)


class TestClamping:
    """Test boundary and clamping logic."""

    def test_clamp_within_bounds(self) -> None:
        assert clamp(50.0, 0.0, 100.0) == 50.0
        assert clamp(0.0, 0.0, 100.0) == 0.0
        assert clamp(100.0, 0.0, 100.0) == 100.0

    def test_clamp_below_min(self) -> None:
        assert clamp(-25.5, 0.0, 100.0) == 0.0

    def test_clamp_above_max(self) -> None:
        assert clamp(150.0, 0.0, 100.0) == 100.0


class TestComponentScores:
    """Test calculation of individual component scores S_G, S_V, S_C, S_P."""

    def test_growth_score_clamping(self) -> None:
        # g_7 = 0.10 (10% growth) -> 0.10 * 500 = 50.0
        metrics = AccountMetrics(followers=5000, growth_rate_7d=0.10)
        res = calculate_ahs(metrics)
        assert res.components.s_g == pytest.approx(50.0)

        # g_7 = 0.30 (30% growth) -> 0.30 * 500 = 150.0 -> clamped to 100
        metrics_high = AccountMetrics(followers=5000, growth_rate_7d=0.30)
        res_high = calculate_ahs(metrics_high)
        assert res_high.components.s_g == 100.0

        # Negative growth -> clamped to 0
        metrics_neg = AccountMetrics(followers=5000, growth_rate_7d=-0.05)
        res_neg = calculate_ahs(metrics_neg)
        assert res_neg.components.s_g == 0.0

    def test_velocity_scores(self) -> None:
        # Rv = 1.0 -> 1.0 * 50 = 50.0
        # Rc = 1.0 -> 1.0 * 50 = 50.0
        metrics = AccountMetrics(
            followers=10000,
            reel_view_velocity_ratio=1.0,
            comment_velocity_ratio=1.0,
        )
        res = calculate_ahs(metrics)
        assert res.components.s_v == pytest.approx(50.0)
        assert res.components.s_c == pytest.approx(50.0)

        # Rv = 3.0 -> 150.0 -> clamped to 100.0
        metrics_viral = AccountMetrics(
            followers=10000,
            reel_view_velocity_ratio=3.0,
            comment_velocity_ratio=2.5,
        )
        res_viral = calculate_ahs(metrics_viral)
        assert res_viral.components.s_v == 100.0
        assert res_viral.components.s_c == 100.0

    def test_post_consistency_score(self) -> None:
        # 12 posts in 30 days -> (12 / 12) * 100 = 100.0
        m1 = AccountMetrics(followers=5000, posts_last_30_days=12)
        assert calculate_ahs(m1).components.s_p == 100.0

        # 6 posts in 30 days -> (6 / 12) * 100 = 50.0
        m2 = AccountMetrics(followers=5000, posts_last_30_days=6)
        assert calculate_ahs(m2).components.s_p == pytest.approx(50.0)

        # 24 posts -> clamped to 100.0
        m3 = AccountMetrics(followers=5000, posts_last_30_days=24)
        assert calculate_ahs(m3).components.s_p == 100.0


class TestBaseAHSFormula:
    """Test Base AHS = 0.35 * S_G + 0.25 * S_V + 0.20 * S_C + 0.20 * S_P."""

    def test_exact_weights(self) -> None:
        # When all components are 100, Base AHS should be exactly 100.0
        metrics = AccountMetrics(
            followers=5000,
            growth_rate_7d=0.20,  # 0.20 * 500 = 100
            reel_view_velocity_ratio=2.0,  # 2.0 * 50 = 100
            comment_velocity_ratio=2.0,  # 2.0 * 50 = 100
            posts_last_30_days=12,  # (12 / 12) * 100 = 100
        )
        res = calculate_ahs(metrics)
        assert res.base_ahs == pytest.approx(100.0)

        # Custom component test:
        # S_G = 50 (g7 = 0.10) -> 0.35 * 50 = 17.5
        # S_V = 60 (Rv = 1.20) -> 0.25 * 60 = 15.0
        # S_C = 40 (Rc = 0.80) -> 0.20 * 40 = 8.0
        # S_P = 50 (P30 = 6)    -> 0.20 * 50 = 10.0
        # Total Base = 17.5 + 15.0 + 8.0 + 10.0 = 50.5
        metrics_custom = AccountMetrics(
            followers=5000,
            growth_rate_7d=0.10,
            reel_view_velocity_ratio=1.20,
            comment_velocity_ratio=0.80,
            posts_last_30_days=6,
        )
        res_custom = calculate_ahs(metrics_custom)
        assert res_custom.base_ahs == pytest.approx(50.5)


class TestDynamicMultipliers:
    """Test dynamic multiplier rules across follower tiers and recency."""

    def test_disqualified_over_100k(self) -> None:
        m, reason = calculate_dynamic_multiplier(followers=100_001, days_since_last_post=1)
        assert m == 0.0
        assert "exceed cap" in reason.lower()

        res = calculate_ahs(AccountMetrics(followers=150_000, growth_rate_7d=0.2))
        assert res.multiplier == 0.0
        assert res.final_ahs == 0.0
        assert not res.is_qualified
        assert "exceed cap" in res.disqualification_reason.lower()

    def test_micro_coach_sweet_spot(self) -> None:
        # Range: 2,000 <= F_t <= 40,000, active (<= 14 days)
        for count in [2000, 12500, 40000]:
            m, reason = calculate_dynamic_multiplier(followers=count, days_since_last_post=2)
            assert m == 1.2
            assert "sweet spot" in reason.lower()

    def test_mid_tier_scaling(self) -> None:
        # Range: 40,000 < F_t <= 100,000
        # At 40,001 -> ~1.0
        m_low, _ = calculate_dynamic_multiplier(followers=40_001, days_since_last_post=1)
        assert 0.99 <= m_low <= 1.0

        # At 70,000 -> 1.0 - 0.2 * (30000/60000) = 0.90
        m_mid, _ = calculate_dynamic_multiplier(followers=70_000, days_since_last_post=1)
        assert m_mid == pytest.approx(0.90, abs=0.01)

        # At 100,000 -> 0.80
        m_high, _ = calculate_dynamic_multiplier(followers=100_000, days_since_last_post=1)
        assert m_high == pytest.approx(0.80, abs=0.01)

    def test_stale_account_penalty(self) -> None:
        # > 14 days since last post -> M = 0.5
        m, reason = calculate_dynamic_multiplier(followers=15_000, days_since_last_post=15)
        assert m == 0.5
        assert "stale" in reason.lower()

        res = calculate_ahs(AccountMetrics(followers=15_000, days_since_last_post=20))
        assert res.multiplier == 0.5

    def test_nano_tier(self) -> None:
        # Under 2,000 followers
        m, reason = calculate_dynamic_multiplier(followers=950, days_since_last_post=1)
        assert m == 0.8
        assert "nano" in reason.lower()


class TestQualificationGate:
    """Test Final AHS >= 60.0 qualification threshold."""

    def test_qualified_micro_coach(self) -> None:
        # Base AHS = 55.0, Micro multiplier = 1.2 -> Final AHS = 66.0 >= 60.0 -> Qualified
        metrics = AccountMetrics(
            followers=12000,
            growth_rate_7d=0.10,  # S_G = 50 (17.5)
            reel_view_velocity_ratio=1.2,  # S_V = 60 (15.0)
            comment_velocity_ratio=1.0,  # S_C = 50 (10.0)
            posts_last_30_days=10,  # S_P = 83.33 (16.67)
            # Base = 59.17 -> Final = 59.17 * 1.2 = 71.0 >= 60.0
        )
        res = calculate_ahs(metrics)
        assert res.is_qualified is True
        assert res.final_ahs >= 60.0
        assert res.disqualification_reason is None

    def test_disqualified_low_score(self) -> None:
        # Sluggish account
        metrics = AccountMetrics(
            followers=8000,
            growth_rate_7d=0.005,  # S_G = 2.5
            reel_view_velocity_ratio=0.4,  # S_V = 20.0
            comment_velocity_ratio=0.3,  # S_C = 15.0
            posts_last_30_days=3,  # S_P = 25.0
        )
        res = calculate_ahs(metrics)
        assert res.is_qualified is False
        assert res.final_ahs < 60.0
        assert "below threshold" in res.disqualification_reason.lower()


class TestEdgeCasesAndZeroDivision:
    """Ensure zero division or extreme numbers never crash the engine."""

    def test_raw_metrics_zero_division(self) -> None:
        raw = AccountMetrics.from_raw_metrics(
            followers=0,
            followers_7d_ago=0,
            v_med_7=0.0,
            v_med_30=0.0,
            c_med_7=0.0,
            c_med_30=0.0,
            posts_30d=0,
            days_since_last_post=0,
        )
        res = calculate_ahs(raw)
        assert res.base_ahs == 0.0
        assert res.final_ahs == 0.0
        assert res.is_qualified is False


class TestAlgorithmicImprovements:
    """Test the VectorLead advanced intelligence metrics (EQS, FMI, Churn, Half-Life)."""

    def test_engagement_quality_score(self) -> None:
        from src.algorithm import AccountMetrics, calculate_ahs

        # 50 comments per 500 likes (10% ratio) + 0.60 reply rate
        m = AccountMetrics(
            followers=10000,
            likes_med_7=500.0,
            comments_med_7=50.0,
            creator_reply_rate=0.60,
        )
        res = calculate_ahs(m)
        assert res.components.s_eqs > 50.0

    def test_follower_churn_disqualification(self) -> None:
        from src.algorithm import AccountMetrics, calculate_ahs

        # 5,000 followers, 7,000 following -> F_ratio = 0.71 < 1.0 -> Disqualified
        churner = AccountMetrics(followers=5000, following=7000)
        res = calculate_ahs(churner)
        assert res.multiplier == 0.0
        assert not res.is_qualified
        assert "churn" in res.disqualification_reason.lower()

    def test_funnel_tier_effects(self) -> None:
        from src.algorithm import AccountMetrics, FunnelTier, calculate_ahs

        high_ticket = AccountMetrics(followers=10000, funnel_tier=FunnelTier.TIER_A_HIGH_TICKET)
        affiliate = AccountMetrics(followers=10000, funnel_tier=FunnelTier.TIER_C_AFFILIATE)

        res_high = calculate_ahs(high_ticket)
        res_aff = calculate_ahs(affiliate)

        assert res_high.multiplier > res_aff.multiplier

    def test_velocity_acceleration_breakout(self) -> None:
        from src.algorithm import AccountMetrics, calculate_ahs

        # Current Rv = 1.6, prior Rv = 1.1 -> delta = +0.5 > 0.20 -> Breakout!
        viral = AccountMetrics(
            followers=15000,
            reel_view_velocity_ratio=1.6,
            prior_reel_view_velocity_ratio=1.1,
        )
        res = calculate_ahs(viral)
        assert res.is_breakout is True

    def test_half_life_recency_decay(self) -> None:
        from src.algorithm import AccountMetrics, calculate_ahs

        fresh = AccountMetrics(followers=10000, posts_last_30_days=12, days_since_last_post=1)
        older = AccountMetrics(followers=10000, posts_last_30_days=12, days_since_last_post=8)

        res_fresh = calculate_ahs(fresh)
        res_older = calculate_ahs(older)

        assert res_fresh.components.s_p > res_older.components.s_p
