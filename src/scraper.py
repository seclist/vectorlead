"""Live Crawler Verification and Profile Extraction Engine.

Uses lightweight crawler headers (e.g. facebookexternalhit/1.1) to extract
real Instagram profile data and verify account existence without session cookies,
browser automation, or expensive proxy pools.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

import requests
from bs4 import BeautifulSoup

from src.algorithm import AccountMetrics, FunnelTier

logger = logging.getLogger(__name__)


def classify_funnel_tier(bio: str, external_url: str | None = None) -> tuple[FunnelTier, bool]:
    """Classify funnel maturity based on external URL domain and caption/bio DM automation triggers."""
    bio_lower = (bio or "").lower()
    url_lower = (external_url or "").lower()

    # Check for DM automation signals (ManyChat triggers)
    dm_automation_patterns = [
        r"comment\s+['\"]?\w+['\"]?",
        r"dm\s+(?:me\s+)?['\"]?(?:ready|coach|scale|fit|start|info|apply|results)['\"]?",
        r"drop\s+(?:a\s+)?['\"]?\w+['\"]?\s+below",
    ]
    has_dm_automation = any(re.search(pat, bio_lower) for pat in dm_automation_patterns)

    tier_a_domains = [
        "calendly.com",
        "typeform.com",
        "forms.gle",
        "skool.com",
        "kajabi.com",
        "stan.store",
        "gohighlevel.com",
        "leadconnectorhq.com",
    ]
    tier_b_domains = ["linktr.ee", "beacons.ai", "bio.fm", "snipfeed.co"]
    tier_c_domains = ["amazon.com", "amzn.to", "shopltk.com", "rewardstyle.com"]

    if any(d in url_lower for d in tier_a_domains) or has_dm_automation:
        return FunnelTier.TIER_A_HIGH_TICKET, has_dm_automation

    if any(d in url_lower for d in tier_b_domains):
        return FunnelTier.TIER_B_MULTI_LINK, has_dm_automation

    if any(d in url_lower for d in tier_c_domains) or "use code" in bio_lower:
        return FunnelTier.TIER_C_AFFILIATE, has_dm_automation

    if url_lower and "instagram.com" not in url_lower:
        return FunnelTier.TIER_A_HIGH_TICKET, has_dm_automation

    return FunnelTier.TIER_D_UNLINKED, has_dm_automation


@dataclass
class InstagramProfile:
    """Extracted Instagram profile metadata."""

    username: str
    exists: bool = True
    full_name: str = ""
    followers: int = 0
    following: int = 0
    posts_count: int = 0
    bio: str = ""
    external_url: str | None = None
    profile_pic_url: str | None = None
    is_verified: bool = False
    is_private: bool = False
    raw_og_description: str = ""
    metrics: AccountMetrics | None = None
    extra_data: dict[str, Any] = field(default_factory=dict)

    @property
    def profile_url(self) -> str:
        clean_handle = self.username.lstrip("@").strip()
        return f"https://www.instagram.com/{clean_handle}/"


class InstagramCrawler:
    """Zero-login profile crawler using social bot headers."""

    DEFAULT_USER_AGENT = "facebookexternalhit/1.1; Facebot; Twitterbot/1.0"

    def __init__(
        self,
        user_agent: str | None = None,
        timeout: int = 10,
        session: requests.Session | None = None,
    ) -> None:
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Fetch-Mode": "navigate",
            }
        )

    @staticmethod
    def clean_handle(username: str) -> str:
        """Strip @ prefix, whitespace, and url parameters."""
        handle = username.strip().lstrip("@")
        if "/" in handle:
            handle = handle.rstrip("/").split("/")[-1]
        return handle.lower()

    @staticmethod
    def parse_count_string(raw: str) -> int:
        """Convert social count strings like '12.5K', '1.2M', '450', '1,200' to integers."""
        if not raw:
            return 0
        raw_clean = raw.strip().upper().replace(",", "").replace(" ", "")

        try:
            if raw_clean.endswith("M"):
                return int(float(raw_clean[:-1]) * 1_000_000)
            if raw_clean.endswith("K"):
                return int(float(raw_clean[:-1]) * 1_000)
            if raw_clean.endswith("B"):
                return int(float(raw_clean[:-1]) * 1_000_000_000)
            return int(float(raw_clean))
        except (ValueError, TypeError):
            return 0

    def parse_html(self, html: str, username: str) -> InstagramProfile | None:
        """Parse profile metadata from crawler HTML responses.

        Returns None if account does not exist or is deleted/unavailable.
        """
        clean_user = self.clean_handle(username)

        # Detect 404 / unavailable signals
        unavailable_signals = [
            "sorry, this page isn't available",
            "page not found",
            "the link you followed may be broken",
            "content isn't available right now",
        ]
        html_lower = html.lower()
        if any(sig in html_lower for sig in unavailable_signals):
            return None

        soup = BeautifulSoup(html, "html.parser")

        # 1. Open Graph Tags
        og_desc_tag = soup.find("meta", property="og:description") or soup.find(
            "meta", attrs={"name": "description"}
        )
        og_title_tag = soup.find("meta", property="og:title")
        og_image_tag = soup.find("meta", property="og:image")
        og_url_tag = soup.find("meta", property="og:url")

        og_desc = og_desc_tag.get("content", "") if og_desc_tag else ""
        og_title = og_title_tag.get("content", "") if og_title_tag else ""
        og_image = og_image_tag.get("content", "") if og_image_tag else ""
        og_url = og_url_tag.get("content", "") if og_url_tag else ""

        if not og_desc and not og_title:
            # If no open graph metadata was found, page is not an active profile
            return None

        followers = 0
        following = 0
        posts_count = 0
        bio = ""
        full_name = ""

        # Pattern: "12.5K Followers, 450 Following, 180 Posts - See Instagram photos and videos from Jane (@jane)"
        # Or: "12.5K Followers, 450 Following, 180 Posts - 1-on-1 Fitness Coach | DM to work | ..."
        desc_pattern = re.search(
            r"([\d\.,\sKMkm]+)\s+Followers,\s+([\d\.,\sKMkm]+)\s+Following,\s+([\d\.,\sKMkm]+)\s+Posts(?:\s*-\s*(.*))?",
            og_desc,
            re.IGNORECASE,
        )

        if desc_pattern:
            followers_str = desc_pattern.group(1)
            following_str = desc_pattern.group(2)
            posts_str = desc_pattern.group(3)
            bio_part = desc_pattern.group(4) or ""

            followers = self.parse_count_string(followers_str)
            following = self.parse_count_string(following_str)
            posts_count = self.parse_count_string(posts_str)

            # Clean trailing boilerplate like "See Instagram photos and videos from ..."
            bio_clean = re.sub(
                r"See Instagram photos and videos from.*$",
                "",
                bio_part,
                flags=re.IGNORECASE,
            ).strip()
            bio = bio_clean.strip(" -•|")

        # Extract full name from og:title: "Jane Doe (@janedoe) • Instagram photos and videos"
        title_pattern = re.search(r"^(.*?)(?:\s*\(@|\s*•|\s*-)", og_title)
        if title_pattern:
            full_name = title_pattern.group(1).strip()
        elif og_title:
            full_name = og_title.split("•")[0].strip()

        # If bio is still empty, look for meta name="description"
        if not bio:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                bio = meta_desc["content"]

        # Synthesize rolling momentum metrics based on live follower & post data
        # (Allows mathematical engine to run immediately on extracted profiles)
        tier, has_dm = classify_funnel_tier(bio, og_url)
        metrics = AccountMetrics.from_raw_metrics(
            followers=followers,
            following=max(50, following),
            followers_7d_ago=int(followers * 0.96) if followers > 0 else 0,  # ~4% growth default
            v_med_7=max(500.0, followers * 0.12),
            v_med_30=max(500.0, followers * 0.10),
            c_med_7=max(10.0, followers * 0.005),
            c_med_30=max(10.0, followers * 0.004),
            likes_med_7=max(20.0, followers * 0.04),
            posts_30d=min(20, max(2, posts_count if posts_count < 20 else 12)),
            days_since_last_post=2,
            funnel_tier=tier,
            has_dm_automation_signal=has_dm,
        )

        return InstagramProfile(
            username=clean_user,
            exists=True,
            full_name=full_name,
            followers=followers,
            following=following,
            posts_count=posts_count,
            bio=bio,
            external_url=og_url or f"https://www.instagram.com/{clean_user}/",
            profile_pic_url=og_image or None,
            raw_og_description=og_desc,
            metrics=metrics,
        )

    def fetch_profile(self, username: str) -> InstagramProfile | None:
        """Fetch profile page using crawler headers and parse metadata."""
        clean_user = self.clean_handle(username)
        target_url = f"https://www.instagram.com/{clean_user}/"

        try:
            response = self.session.get(target_url, timeout=self.timeout)
            if response.status_code == 404:
                logger.info("Account @%s returned 404 (does not exist).", clean_user)
                return None
            if response.status_code != 200:
                logger.warning(
                    "Unexpected status code %d for @%s", response.status_code, clean_user
                )
                return None

            return self.parse_html(response.text, clean_user)
        except requests.RequestException as e:
            logger.error("Request failed while fetching @%s: %s", clean_user, e)
            return None


def get_curated_seed_prospects(niche: str = "personal_trainer") -> list[dict[str, Any]]:
    """Return a curated pool of candidate accounts with realistic diversity for testing and hunting."""
    if niche == "realtor":
        return [
            {
                "username": "sarah_austin_realtor",
                "full_name": "Sarah Miller | Austin Realtor",
                "followers": 14200,
                "posts_count": 280,
                "bio": "Austin Luxury Real Estate Agent 🏡 Helping buyers & sellers. Book a showing or DM for home valuation 👇",
                "metrics": AccountMetrics(
                    followers=14200,
                    growth_rate_7d=0.08,
                    reel_view_velocity_ratio=1.4,
                    comment_velocity_ratio=1.2,
                    posts_last_30_days=14,
                    days_since_last_post=1,
                ),
            },
            {
                "username": "austin_building_materials",
                "full_name": "Texas Construction & Building",
                "followers": 45000,
                "posts_count": 520,
                "bio": "Wholesale building materials and hardware store. Construction equipment. Free shipping on bulk orders.",
                "metrics": AccountMetrics(
                    followers=45000,
                    growth_rate_7d=0.01,
                    reel_view_velocity_ratio=0.8,
                    comment_velocity_ratio=0.5,
                    posts_last_30_days=4,
                    days_since_last_post=3,
                ),
            },
            {
                "username": "dallas_homes_marcus",
                "full_name": "Marcus Vance | Dallas Broker Associate",
                "followers": 28500,
                "posts_count": 410,
                "bio": "Dallas Real Estate Broker 🔑 Relocation specialist. Schedule consultation or view listings via link in bio!",
                "metrics": AccountMetrics(
                    followers=28500,
                    growth_rate_7d=0.05,
                    reel_view_velocity_ratio=1.1,
                    comment_velocity_ratio=1.0,
                    posts_last_30_days=11,
                    days_since_last_post=2,
                ),
            },
            {
                "username": "zillow_celebrity_mansions",
                "full_name": "Celebrity Mansions & Megahomes",
                "followers": 850000,
                "posts_count": 2100,
                "bio": "Touring $50M mega mansions around the globe. Tag us to be featured.",
                "metrics": AccountMetrics(
                    followers=850000,
                    growth_rate_7d=0.02,
                    reel_view_velocity_ratio=1.0,
                    comment_velocity_ratio=1.0,
                    posts_last_30_days=30,
                    days_since_last_post=1,
                ),
            },
        ]

    # Default: personal_trainer pool
    return [
        {
            "username": "alex_hypertrophy_coach",
            "full_name": "Alex Carter | Online Coach",
            "followers": 18500,
            "posts_count": 340,
            "bio": "Online Fitness Coach & Hypertrophy Specialist 🔥 100+ transformations. 1-on-1 coaching application 👇 Apply below!",
            "metrics": AccountMetrics(
                followers=18500,
                growth_rate_7d=0.11,
                reel_view_velocity_ratio=1.6,
                comment_velocity_ratio=1.3,
                posts_last_30_days=16,
                days_since_last_post=1,
            ),
        },
        {
            "username": "aesthetic_gymwear_co",
            "full_name": "Aesthetic Gymwear Brand",
            "followers": 52000,
            "posts_count": 610,
            "bio": "Premium gym clothing & activewear for bodybuilders. Worldwide shipping 📦 Shop our summer drop now!",
            "metrics": AccountMetrics(
                followers=52000,
                growth_rate_7d=0.03,
                reel_view_velocity_ratio=0.9,
                comment_velocity_ratio=0.7,
                posts_last_30_days=12,
                days_since_last_post=2,
            ),
        },
        {
            "username": "coach_elena_fitness",
            "full_name": "Elena Rostova | Fat Loss Specialist",
            "followers": 9400,
            "posts_count": 190,
            "bio": "Certified Personal Trainer helping busy women drop 15-30lbs. DM for coaching or apply below 👇",
            "metrics": AccountMetrics(
                followers=9400,
                growth_rate_7d=0.09,
                reel_view_velocity_ratio=1.3,
                comment_velocity_ratio=1.1,
                posts_last_30_days=13,
                days_since_last_post=1,
            ),
        },
        {
            "username": "mega_fitness_celeb",
            "full_name": "Celebrity Fitness Icon",
            "followers": 1450000,
            "posts_count": 3200,
            "bio": "Actor, Author, World Champion. Business inquiries: management@celebfitness.com",
            "metrics": AccountMetrics(
                followers=1450000,
                growth_rate_7d=0.01,
                reel_view_velocity_ratio=0.8,
                comment_velocity_ratio=0.6,
                posts_last_30_days=10,
                days_since_last_post=1,
            ),
        },
        {
            "username": "sam_lifts_daily",
            "full_name": "Sam R",
            "followers": 3200,
            "posts_count": 75,
            "bio": "Fitness coach and gym rat. Sharing my bench and squat PRs. Coffee addict. Seattle 📍",
            "metrics": AccountMetrics(
                followers=3200,
                growth_rate_7d=0.02,
                reel_view_velocity_ratio=0.7,
                comment_velocity_ratio=0.4,
                posts_last_30_days=4,
                days_since_last_post=3,
            ),
        },
        {
            "username": "deleted_dead_account_404",
            "full_name": "",
            "followers": 0,
            "posts_count": 0,
            "bio": "",
            "exists": False,
            "metrics": None,
        },
        {
            "username": "marcus_strength_conditioning",
            "full_name": "Marcus Vance, CSCS",
            "followers": 24000,
            "posts_count": 480,
            "bio": "Strength & conditioning coach for combat athletes. 1:1 coaching slots open. Apply below 👇",
            "metrics": AccountMetrics(
                followers=24000,
                growth_rate_7d=0.14,
                reel_view_velocity_ratio=1.7,
                comment_velocity_ratio=1.4,
                posts_last_30_days=18,
                days_since_last_post=1,
            ),
        },
        {
            "username": "dormant_coach_dan",
            "full_name": "Dan Fitness",
            "followers": 12000,
            "posts_count": 150,
            "bio": "Online coach. Taking a social media break.",
            "metrics": AccountMetrics(
                followers=12000,
                growth_rate_7d=0.001,
                reel_view_velocity_ratio=0.2,
                comment_velocity_ratio=0.1,
                posts_last_30_days=1,
                days_since_last_post=35,
            ),
        },
        {
            "username": "chloe_mobility_coach",
            "full_name": "Chloe Lin | Mobility & Posture",
            "followers": 31500,
            "posts_count": 520,
            "bio": "Mobility Coach | Bulletproof your joints. Link in bio for custom workout programs & 1-on-1 coaching!",
            "metrics": AccountMetrics(
                followers=31500,
                growth_rate_7d=0.12,
                reel_view_velocity_ratio=1.5,
                comment_velocity_ratio=1.3,
                posts_last_30_days=15,
                days_since_last_post=1,
            ),
        },
        {
            "username": "supplements_direct_store",
            "full_name": "Supplements Direct",
            "followers": 89000,
            "posts_count": 1100,
            "bio": "Discount supplements store. Free shipping on all orders over $50. Shop now!",
            "metrics": AccountMetrics(
                followers=89000,
                growth_rate_7d=0.01,
                reel_view_velocity_ratio=0.6,
                comment_velocity_ratio=0.4,
                posts_last_30_days=20,
                days_since_last_post=1,
            ),
        },
        {
            "username": "jordan_calisthenics_prep",
            "full_name": "Jordan Cole | Calisthenics Coach",
            "followers": 16800,
            "posts_count": 270,
            "bio": "Calisthenics coach & body transformation. Master bodyweight mastery. 1-on-1 coaching spots open 👇",
            "metrics": AccountMetrics(
                followers=16800,
                growth_rate_7d=0.10,
                reel_view_velocity_ratio=1.4,
                comment_velocity_ratio=1.2,
                posts_last_30_days=14,
                days_since_last_post=2,
            ),
        },
        {
            "username": "kyle_physique_online",
            "full_name": "Kyle Turner | Physique Coach",
            "followers": 22400,
            "posts_count": 390,
            "bio": "Online fitness coach helping dads get shredded. Custom nutrition & training. Apply below 👇",
            "metrics": AccountMetrics(
                followers=22400,
                growth_rate_7d=0.13,
                reel_view_velocity_ratio=1.5,
                comment_velocity_ratio=1.3,
                posts_last_30_days=15,
                days_since_last_post=1,
            ),
        },
        {
            "username": "tara_strength_system",
            "full_name": "Tara Green | Strength Coach",
            "followers": 15100,
            "posts_count": 310,
            "bio": "Powerlifting & strength coach. DM 'ready' to join the team. 1-on-1 coaching link in bio!",
            "metrics": AccountMetrics(
                followers=15100,
                growth_rate_7d=0.09,
                reel_view_velocity_ratio=1.3,
                comment_velocity_ratio=1.2,
                posts_last_30_days=14,
                days_since_last_post=2,
            ),
        },
        {
            "username": "ben_fatloss_blueprint",
            "full_name": "Ben Brooks | Fat Loss Specialist",
            "followers": 19800,
            "posts_count": 420,
            "bio": "Online personal trainer. Lose fat without cutting carbs. Custom workout & diet. Apply below!",
            "metrics": AccountMetrics(
                followers=19800,
                growth_rate_7d=0.11,
                reel_view_velocity_ratio=1.6,
                comment_velocity_ratio=1.4,
                posts_last_30_days=16,
                days_since_last_post=1,
            ),
        },
        {
            "username": "ryan_kettlebell_coach",
            "full_name": "Ryan Ross | Kettlebell Coach",
            "followers": 11300,
            "posts_count": 230,
            "bio": "Kettlebell coach & functional fitness. 1:1 coaching & custom nutrition. Link in bio to apply!",
            "metrics": AccountMetrics(
                followers=11300,
                growth_rate_7d=0.08,
                reel_view_velocity_ratio=1.2,
                comment_velocity_ratio=1.1,
                posts_last_30_days=12,
                days_since_last_post=1,
            ),
        },
        {
            "username": "zoe_prep_coach",
            "full_name": "Zoe Adams | Bikini & Prep Coach",
            "followers": 27900,
            "posts_count": 460,
            "bio": "Physique coach & competition prep. Client results speak for themselves. DM for coaching!",
            "metrics": AccountMetrics(
                followers=27900,
                growth_rate_7d=0.12,
                reel_view_velocity_ratio=1.5,
                comment_velocity_ratio=1.3,
                posts_last_30_days=16,
                days_since_last_post=1,
            ),
        },
    ]
