"""VectorLead: Account Health Score (AHS) Mathematical Momentum Engine.

Implements the advanced rolling 35-day momentum formula enhanced with:
1. Engagement Quality Score (EQS) & bot pod detection
2. Funnel Maturity Index (FMI) & link intent classification
3. Half-life exponential recency decay on post frequency
4. Follower-to-following churn filter (F_ratio)
5. Velocity acceleration (second derivative breakout detection)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum


def clamp(value: float, min_val: float = 0.0, max_val: float = 100.0) -> float:
    """Clamp a numerical value between min_val and max_val."""
    return max(min_val, min(max_val, float(value)))


class FunnelTier(StrEnum):
    """Categorized funnel maturity based on link destination and DM automation."""

    TIER_A_HIGH_TICKET = "high_ticket"  # Calendly, Typeform, Skool, Kajabi, Stan Store, ManyChat
    TIER_B_MULTI_LINK = "multi_link"  # Linktree, Beacons, Bio.fm
    TIER_C_AFFILIATE = "affiliate"  # Amazon storefront, LTK, discount codes
    TIER_D_UNLINKED = "unlinked"  # No link or inactive bio


@dataclass(frozen=True)
class ComponentScores:
    """Individual clamped component scores (0 to 100) for VectorLead AHS computation."""

    s_g: float  # Follower growth score
    s_v: float  # Reel view velocity score
    s_c: float  # Comment velocity score
    s_p: float  # Post consistency score (exponential decay weighted)
    s_eqs: float = 50.0  # Engagement Quality Score (comment depth & authentic interaction)

    def as_dict(self) -> dict[str, float]:
        return {
            "s_g": round(self.s_g, 2),
            "s_v": round(self.s_v, 2),
            "s_c": round(self.s_c, 2),
            "s_p": round(self.s_p, 2),
            "s_eqs": round(self.s_eqs, 2),
        }


@dataclass(frozen=True)
class AccountMetrics:
    """Standardized input metrics for calculating an account's AHS."""

    followers: int
    following: int = 500
    growth_rate_7d: float = 0.02
    reel_view_velocity_ratio: float = 1.0
    prior_reel_view_velocity_ratio: float = 1.0  # For velocity acceleration
    comment_velocity_ratio: float = 1.0
    posts_last_30_days: int = 12
    days_since_last_post: int = 1
    likes_med_7: float = 250.0
    comments_med_7: float = 15.0
    creator_reply_rate: float = 0.45  # Proportion of comments creator replies to
    funnel_tier: FunnelTier = FunnelTier.TIER_A_HIGH_TICKET
    has_dm_automation_signal: bool = False  # E.g. "Comment 'READY'" or "DM 'SCALE'"

    @classmethod
    def from_raw_metrics(
        cls,
        followers: int,
        following: int = 500,
        followers_7d_ago: int | None = None,
        v_med_7: float = 1000.0,
        v_med_30: float = 1000.0,
        v_med_prior_7: float | None = None,
        c_med_7: float = 25.0,
        c_med_30: float = 25.0,
        likes_med_7: float = 500.0,
        posts_30d: int = 12,
        days_since_last_post: int = 1,
        creator_reply_rate: float = 0.45,
        funnel_tier: FunnelTier = FunnelTier.TIER_A_HIGH_TICKET,
        has_dm_automation_signal: bool = False,
    ) -> AccountMetrics:
        """Construct AccountMetrics from raw historical medians and counts."""
        if followers_7d_ago is not None:
            baseline = max(followers_7d_ago, 1)
            growth_rate_7d = (followers - followers_7d_ago) / baseline
        else:
            growth_rate_7d = 0.02

        rv = v_med_7 / max(v_med_30, 1.0)
        rv_prior = (v_med_prior_7 / max(v_med_30, 1.0)) if v_med_prior_7 is not None else rv
        rc = c_med_7 / max(c_med_30, 1.0)

        return cls(
            followers=max(0, followers),
            following=max(0, following),
            growth_rate_7d=growth_rate_7d,
            reel_view_velocity_ratio=rv,
            prior_reel_view_velocity_ratio=rv_prior,
            comment_velocity_ratio=rc,
            posts_last_30_days=max(0, posts_30d),
            days_since_last_post=max(0, days_since_last_post),
            likes_med_7=max(0.0, likes_med_7),
            comments_med_7=max(0.0, c_med_7),
            creator_reply_rate=clamp(creator_reply_rate, 0.0, 1.0),
            funnel_tier=funnel_tier,
            has_dm_automation_signal=has_dm_automation_signal,
        )


@dataclass(frozen=True)
class AHSResult:
    """Result of Account Health Score calculation including subscores and verdicts."""

    base_ahs: float
    multiplier: float
    final_ahs: float
    multiplier_reason: str
    components: ComponentScores
    is_qualified: bool
    is_breakout: bool = False
    f_ratio: float = 1.0
    funnel_tier: FunnelTier = FunnelTier.TIER_A_HIGH_TICKET
    disqualification_reason: str | None = None
    breakdown: dict[str, float] = field(default_factory=dict)

    def summary(self) -> str:
        status = (
            "QUALIFIED" if self.is_qualified else f"DISQUALIFIED ({self.disqualification_reason})"
        )
        breakout_tag = " [BREAKOUT ACCELERATION 🚀]" if self.is_breakout else ""
        return f"AHS: {self.final_ahs:.1f} (Base: {self.base_ahs:.1f} × {self.multiplier:.2f}){breakout_tag} -> {status}"


@dataclass(frozen=True)
class MultiplierResult:
    """Multiplier calculation result supporting both 2-tuple unpacking and field access."""

    multiplier: float
    reason: str
    is_breakout: bool = False
    f_ratio: float = 1.0

    def __iter__(self):
        yield self.multiplier
        yield self.reason


def calculate_dynamic_multiplier(
    followers: int,
    days_since_last_post: int,
    following: int = 500,
    funnel_tier: FunnelTier = FunnelTier.TIER_A_HIGH_TICKET,
    has_dm_automation: bool = False,
    velocity_acceleration: float = 0.0,
    max_followers_cap: int = 100_000,
) -> MultiplierResult:
    """Calculate the multi-factor dynamic multiplier M.

    Returns a MultiplierResult that can be unpacked as `m, reason = ...` or accessed directly.
    """
    # 1. Base Follower Cap
    if followers > max_followers_cap:
        return MultiplierResult(
            multiplier=0.0,
            reason=f"Followers ({followers:,}) exceed cap of {max_followers_cap:,}",
            is_breakout=False,
            f_ratio=0.0,
        )

    # 2. Follower-to-Following Churn Ratio
    f_ratio = round(followers / max(following, 1), 2)
    if followers >= 1_000 and f_ratio < 1.0:
        return MultiplierResult(
            multiplier=0.0,
            reason=f"Disqualified: Excessive following-to-follower churn (F_ratio: {f_ratio:.2f})",
            is_breakout=False,
            f_ratio=f_ratio,
        )

    # 3. Recency / Dormancy Check
    if days_since_last_post > 14:
        return MultiplierResult(
            multiplier=0.5,
            reason=f"Stale account: {days_since_last_post} days since last post (>14d)",
            is_breakout=False,
            f_ratio=f_ratio,
        )

    # 4. Follower Tier Baseline
    if 2_000 <= followers <= 40_000:
        m_tier = 1.2
        tier_reason = "Micro-coach sweet spot (2,000 - 40,000 followers, active)"
    elif 40_000 < followers <= 100_000:
        ratio = (followers - 40_000) / 60_000
        m_tier = round(1.0 - (0.2 * ratio), 3)
        tier_reason = f"Mid-tier creator ({followers:,} followers)"
    else:
        m_tier = 0.8
        tier_reason = f"Nano creator ({followers:,} followers, baseline proof)"

    # 5. Churn Modifier (only applied if followers >= 1000)
    m_churn = 0.85 if (1.0 <= f_ratio < 2.0 and followers >= 1000) else 1.0

    # 6. Funnel Maturity Modifier (only if not default high_ticket)
    if has_dm_automation or funnel_tier == FunnelTier.TIER_A_HIGH_TICKET:
        m_funnel = 1.0
    elif funnel_tier == FunnelTier.TIER_B_MULTI_LINK:
        m_funnel = 0.95
    elif funnel_tier == FunnelTier.TIER_C_AFFILIATE:
        m_funnel = 0.75
    else:
        m_funnel = 0.85

    # 7. Velocity Acceleration (Breakout Detection)
    is_breakout = False
    m_accel = 1.0
    if velocity_acceleration > 0.20:
        is_breakout = True
        m_accel = 1.10

    # Combine multipliers smoothly
    final_m = round(m_tier * m_churn * m_funnel * m_accel, 3)
    return MultiplierResult(
        multiplier=final_m,
        reason=tier_reason,
        is_breakout=is_breakout,
        f_ratio=f_ratio,
    )


def calculate_ahs(
    metrics: AccountMetrics,
    min_qualification_ahs: float = 60.0,
    max_followers_cap: int = 100_000,
    use_advanced_weights: bool = False,
) -> AHSResult:
    """Calculate the Account Health Score (AHS) using the enhanced momentum formula.

    Component Scores (Clamped 0 - 100):
      S_G   = clamp(g_7 * 500, 0, 100)
      S_V   = clamp(R_v * 50, 0, 100)
      S_C   = clamp(R_c * 50, 0, 100)
      S_P   = clamp((P_eff / 12) * 100, 0, 100)  [Exponential half-life decay]
      S_EQS = clamp((Comments/Likes) * 1000 + Reply_Rate * 20, 0, 100)

    Base Score Weights:
      Standard Mode (default): 0.35 S_G + 0.25 S_V + 0.20 S_C + 0.20 S_P
      Advanced Mode: 0.30 S_G + 0.20 S_V + 0.15 S_C + 0.15 S_P + 0.20 S_EQS

    Final Score:
      Final AHS = Base AHS * Multiplier (M)
    """
    # 1. Growth Score
    s_g = clamp(metrics.growth_rate_7d * 500.0, 0.0, 100.0)

    # 2. Reel View Velocity Score
    s_v = clamp(metrics.reel_view_velocity_ratio * 50.0, 0.0, 100.0)

    # 3. Comment Velocity Score
    s_c = clamp(metrics.comment_velocity_ratio * 50.0, 0.0, 100.0)

    # 4. Post Consistency with Exponential Recency Decay (lambda = 7 days)
    decay_factor = math.exp(-max(0, metrics.days_since_last_post - 1) / 7.0)
    p_eff = metrics.posts_last_30_days * decay_factor
    s_p = clamp((p_eff / 12.0) * 100.0, 0.0, 100.0)

    # 5. Engagement Quality Score (EQS) & Comment Authenticity
    if metrics.followers == 0 and metrics.comments_med_7 == 0.0:
        s_eqs = 0.0
    else:
        comment_to_like_ratio = metrics.comments_med_7 / max(metrics.likes_med_7, 1.0)
        eqs_raw = (comment_to_like_ratio * 1000.0) + (metrics.creator_reply_rate * 25.0)
        s_eqs = clamp(eqs_raw, 0.0, 100.0)

    components = ComponentScores(s_g=s_g, s_v=s_v, s_c=s_c, s_p=s_p, s_eqs=s_eqs)

    # 6. Base AHS
    if use_advanced_weights:
        base_ahs = (0.30 * s_g) + (0.20 * s_v) + (0.15 * s_c) + (0.15 * s_p) + (0.20 * s_eqs)
    else:
        base_ahs = (0.35 * s_g) + (0.25 * s_v) + (0.20 * s_c) + (0.20 * s_p)

    # 7. Velocity Acceleration
    accel = metrics.reel_view_velocity_ratio - metrics.prior_reel_view_velocity_ratio

    # 8. Dynamic Multiplier
    res_m = calculate_dynamic_multiplier(
        followers=metrics.followers,
        days_since_last_post=metrics.days_since_last_post,
        following=metrics.following,
        funnel_tier=metrics.funnel_tier,
        has_dm_automation=metrics.has_dm_automation_signal,
        velocity_acceleration=accel,
        max_followers_cap=max_followers_cap,
    )
    multiplier = res_m.multiplier
    reason = res_m.reason
    is_breakout = res_m.is_breakout
    f_ratio = res_m.f_ratio

    # 9. Final Score
    final_ahs = round(base_ahs * multiplier, 2)

    # 10. Qualification Gate
    is_qualified = True
    disqualification_reason: str | None = None

    if multiplier == 0.0:
        is_qualified = False
        disqualification_reason = reason
    elif final_ahs < min_qualification_ahs:
        is_qualified = False
        disqualification_reason = (
            f"AHS {final_ahs:.1f} below threshold of {min_qualification_ahs:.1f}"
        )

    breakdown = {
        "s_g": round(s_g, 1),
        "s_v": round(s_v, 1),
        "s_c": round(s_c, 1),
        "s_p": round(s_p, 1),
        "s_eqs": round(s_eqs, 1),
        "p_eff": round(p_eff, 1),
        "f_ratio": f_ratio,
        "accel": round(accel, 2),
    }

    return AHSResult(
        base_ahs=round(base_ahs, 2),
        multiplier=multiplier,
        final_ahs=final_ahs,
        multiplier_reason=reason,
        components=components,
        is_qualified=is_qualified,
        is_breakout=is_breakout,
        f_ratio=f_ratio,
        funnel_tier=metrics.funnel_tier,
        disqualification_reason=disqualification_reason,
        breakdown=breakdown,
    )
