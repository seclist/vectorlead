"""Unit tests for the live crawler and profile extraction engine."""

from src.scraper import InstagramCrawler


class TestCrawlerHelpers:
    """Test string parsing and cleaning helpers."""

    def test_clean_handle(self) -> None:
        assert InstagramCrawler.clean_handle("@coach_mike") == "coach_mike"
        assert InstagramCrawler.clean_handle("coach_mike") == "coach_mike"
        assert (
            InstagramCrawler.clean_handle("https://www.instagram.com/coach_mike/") == "coach_mike"
        )
        assert InstagramCrawler.clean_handle("  @Coach_Mike  ") == "coach_mike"

    def test_parse_count_string(self) -> None:
        assert InstagramCrawler.parse_count_string("450") == 450
        assert InstagramCrawler.parse_count_string("1,200") == 1200
        assert InstagramCrawler.parse_count_string("12.5K") == 12500
        assert InstagramCrawler.parse_count_string("1.2M") == 1200000
        assert InstagramCrawler.parse_count_string("3.4k") == 3400
        assert InstagramCrawler.parse_count_string("1.5B") == 1500000000
        assert InstagramCrawler.parse_count_string("") == 0
        assert InstagramCrawler.parse_count_string("invalid") == 0


class TestHtmlParsing:
    """Test extracting profile data from OpenGraph crawler responses."""

    def test_parse_active_profile(self) -> None:
        crawler = InstagramCrawler()
        sample_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta property="og:title" content="Mike Miller (@coachmikemiller) • Instagram photos and videos" />
            <meta property="og:description" content="14.2K Followers, 380 Following, 210 Posts - Online Fitness Coach & Personal Trainer | 1-on-1 coaching application. Apply below 👇" />
            <meta property="og:url" content="https://www.instagram.com/coachmikemiller/" />
            <meta property="og:image" content="https://instagram.example.com/avatar.jpg" />
        </head>
        <body></body>
        </html>
        """
        profile = crawler.parse_html(sample_html, "coachmikemiller")
        assert profile is not None
        assert profile.exists is True
        assert profile.username == "coachmikemiller"
        assert profile.full_name == "Mike Miller"
        assert profile.followers == 14200
        assert profile.following == 380
        assert profile.posts_count == 210
        assert "Online Fitness Coach" in profile.bio
        assert profile.metrics is not None
        assert profile.metrics.followers == 14200

    def test_parse_404_page(self) -> None:
        crawler = InstagramCrawler()
        sample_404_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Page Not Found • Instagram</title></head>
        <body>
            <h2>Sorry, this page isn't available.</h2>
            <p>The link you followed may be broken, or the page may have been removed.</p>
        </body>
        </html>
        """
        profile = crawler.parse_html(sample_404_html, "deleted_account_handle")
        assert profile is None

    def test_parse_empty_page(self) -> None:
        crawler = InstagramCrawler()
        profile = crawler.parse_html("<html><body>Empty</body></html>", "some_user")
        assert profile is None


class TestFunnelClassification:
    """Test Funnel Maturity Index (FMI) domain and DM automation detection."""

    def test_high_ticket_calendly(self) -> None:
        from src.algorithm import FunnelTier
        from src.scraper import classify_funnel_tier

        tier, has_dm = classify_funnel_tier(
            bio="Online Coach | Book a call",
            external_url="https://calendly.com/coach/call",
        )
        assert tier == FunnelTier.TIER_A_HIGH_TICKET

    def test_dm_automation_trigger(self) -> None:
        from src.algorithm import FunnelTier
        from src.scraper import classify_funnel_tier

        tier, has_dm = classify_funnel_tier(
            bio="Want my fat loss roadmap? Comment 'READY' below and I'll DM you",
            external_url="https://instagram.com/mybio",
        )
        assert tier == FunnelTier.TIER_A_HIGH_TICKET
        assert has_dm is True

    def test_multilink_tree(self) -> None:
        from src.algorithm import FunnelTier
        from src.scraper import classify_funnel_tier

        tier, has_dm = classify_funnel_tier(
            bio="Fitness tips and recipes",
            external_url="https://linktr.ee/myprofile",
        )
        assert tier == FunnelTier.TIER_B_MULTI_LINK

    def test_affiliate_amazon(self) -> None:
        from src.algorithm import FunnelTier
        from src.scraper import classify_funnel_tier

        tier, has_dm = classify_funnel_tier(
            bio="My gym favorites & workout gear. Use code GAINS for 10% off",
            external_url="https://amazon.com/shop/influencer",
        )
        assert tier == FunnelTier.TIER_C_AFFILIATE
