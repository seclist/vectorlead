"""Unit tests for the modular NLP and keyword niche classifier."""

import pytest
from src.classifier import NicheClassifier, NicheDefinition


@pytest.fixture
def classifier() -> NicheClassifier:
    """Initialize classifier with config/niches.yaml."""
    return NicheClassifier()


class TestPersonalTrainerNiche:
    """Test qualification rules for personal_trainer niche."""

    def test_ideal_personal_trainer_matches(self, classifier: NicheClassifier) -> None:
        bio = (
            "🔥 Online Fitness Coach | 100+ Transformations\n"
            "Helping busy pros drop 20lbs & build muscle\n"
            "📲 1-on-1 Coaching | Spots Limited\n"
            "Apply below 👇 linktr.ee/coachmike"
        )
        verdict = classifier.evaluate(
            bio=bio,
            full_name="Mike Miller | Online Fitness Coach",
            username="coachmikemiller",
            external_url="https://linktr.ee/coachmike",
            niche_id="personal_trainer",
        )
        assert verdict.is_match is True
        assert verdict.confidence >= 0.70
        assert "fitness coach" in verdict.matched_positives or "online coach" in verdict.matched_positives
        assert "1-on-1 coaching" in verdict.matched_services or "apply below" in verdict.matched_services
        assert len(verdict.matched_negatives) == 0
        assert verdict.disqualification_reason is None

    def test_clothing_brand_disqualified(self, classifier: NicheClassifier) -> None:
        bio = (
            "Premium gym clothing & activewear designed for lifters.\n"
            "Shop our new summer drop now! Free shipping worldwide.\n"
            "Use code GAINS for 15% off"
        )
        verdict = classifier.evaluate(
            bio=bio,
            full_name="Aesthetic Gymwear Brand",
            username="aestheticgymwear",
            niche_id="personal_trainer",
        )
        assert verdict.is_match is False
        assert len(verdict.matched_negatives) > 0
        assert any(k in verdict.matched_negatives for k in ["gym clothing", "apparel", "activewear", "free shipping", "shop now"])
        assert "negative keyword" in verdict.disqualification_reason.lower()

    def test_supplement_store_disqualified(self, classifier: NicheClassifier) -> None:
        bio = "The purest whey protein and pre-workout on the market. Supplements store. Shop now!"
        verdict = classifier.evaluate(bio=bio, full_name="Alpha Nutrition", niche_id="personal_trainer")
        assert verdict.is_match is False
        assert "supplements store" in verdict.matched_negatives or "shop now" in verdict.matched_negatives

    def test_passive_fitness_enthusiast_disqualified(self, classifier: NicheClassifier) -> None:
        # Has positive keywords (fitness coach, personal trainer) but no high-ticket service indicator
        bio = "Certified Personal Trainer & Fitness Coach sharing daily gym workouts and meals. Dog dad. Seattle 📍"
        verdict = classifier.evaluate(
            bio=bio,
            full_name="Alex R | Trainer",
            username="alex_lifts",
            niche_id="personal_trainer",
        )
        assert verdict.is_match is False
        assert "missing high-ticket service indicators" in verdict.disqualification_reason.lower()

    def test_unrelated_profile_disqualified(self, classifier: NicheClassifier) -> None:
        bio = "Software engineer building AI tools. Coffee, photography, and travel."
        verdict = classifier.evaluate(
            bio=bio,
            full_name="David Tech",
            username="david_codes",
            niche_id="personal_trainer",
        )
        assert verdict.is_match is False
        assert "no domain keywords matched" in verdict.disqualification_reason.lower()


class TestModularNiches:
    """Test that multiple niches loaded from YAML function independently."""

    def test_realtor_niche(self, classifier: NicheClassifier) -> None:
        bio = (
            "Top Austin Realtor 🏡 | Luxury Real Estate Specialist\n"
            "Helping families buy and sell dream homes\n"
            "Selling your home? Book a showing or DM for valuation 👇"
        )
        verdict = classifier.evaluate(
            bio=bio,
            full_name="Sarah Jenkins Realtor",
            username="sarah_austin_homes",
            niche_id="realtor",
        )
        assert verdict.is_match is True
        assert "realtor" in verdict.matched_positives or "luxury real estate" in verdict.matched_positives

    def test_realtor_disqualifies_hardware_store(self, classifier: NicheClassifier) -> None:
        bio = "Austin construction materials and hardware store. Free shipping on bulk orders."
        verdict = classifier.evaluate(
            bio=bio,
            full_name="Austin Hardware",
            username="austin_hardware",
            niche_id="realtor",
        )
        assert verdict.is_match is False
        assert len(verdict.matched_negatives) > 0

    def test_ecommerce_niche(self, classifier: NicheClassifier) -> None:
        bio = (
            "Shopify mentor & E-commerce coach 🚀\n"
            "Helped 50+ students hit $50k/mo\n"
            "Apply for mentorship below 👇"
        )
        verdict = classifier.evaluate(
            bio=bio,
            full_name="Jason Ecom",
            username="jasonecom",
            niche_id="ecommerce",
        )
        assert verdict.is_match is True
        assert any(k in verdict.matched_positives for k in ["ecommerce coach", "shopify mentor"])

    def test_unknown_niche(self, classifier: NicheClassifier) -> None:
        verdict = classifier.evaluate(bio="test bio", niche_id="nonexistent_niche")
        assert verdict.is_match is False
        assert "unknown niche" in verdict.disqualification_reason.lower()


class TestDynamicRegistration:
    """Test dynamically registering a niche at runtime."""

    def test_register_custom_niche(self, classifier: NicheClassifier) -> None:
        custom = NicheDefinition(
            id="guitar_teacher",
            name="Online Guitar Instructor",
            description="Private guitar tutors",
            positive_keywords=["guitar teacher", "guitar lessons"],
            service_indicators=["book a lesson", "1-on-1 lessons"],
            negative_keywords=["guitar factory", "buy guitars"],
        )
        classifier.register_niche(custom)
        assert "guitar_teacher" in classifier.list_niches()

        verdict = classifier.evaluate(
            bio="Online guitar lessons for beginners. Book a lesson below!",
            niche_id="guitar_teacher",
        )
        assert verdict.is_match is True
