"""Modular NLP and Keyword Niche Qualification Engine.

Loads niche criteria from YAML or memory, evaluates Instagram profile metadata
(bio, full name, username, links) against positive domain keywords, high-ticket
service indicator signals, and strict negative exclusion filters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class NicheDefinition:
    """Configuration for an individual niche."""

    id: str
    name: str
    description: str
    positive_keywords: list[str] = field(default_factory=list)
    service_indicators: list[str] = field(default_factory=list)
    negative_keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NicheVerdict:
    """Evaluation verdict for a prospect against a specific niche."""

    niche: str
    is_match: bool
    confidence: float
    matched_positives: list[str]
    matched_services: list[str]
    matched_negatives: list[str]
    disqualification_reason: str | None = None

    def summary(self) -> str:
        if self.is_match:
            return (
                f"MATCH [{self.niche}] (Confidence: {self.confidence:.0%}) "
                f"| Positives: {len(self.matched_positives)} | Services: {len(self.matched_services)}"
            )
        return f"REJECT [{self.niche}] -> {self.disqualification_reason}"


class NicheClassifier:
    """Evaluates candidate profiles against modular niche rules."""

    DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "niches.yaml"

    def __init__(self, config_path: Path | str | None = None) -> None:
        self.niches: dict[str, NicheDefinition] = {}
        path = Path(config_path) if config_path else self.DEFAULT_CONFIG_PATH
        if path.exists():
            self.load_from_yaml(path)
        else:
            self._load_fallback_defaults()

    def load_from_yaml(self, path: Path | str) -> None:
        """Load niche configurations from a YAML file."""
        path_obj = Path(path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Niche configuration file not found: {path}")

        with open(path_obj, encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}

        raw_niches = data.get("niches", {})
        self.niches.clear()
        for niche_id, cfg in raw_niches.items():
            self.niches[niche_id] = NicheDefinition(
                id=niche_id,
                name=cfg.get("name", niche_id),
                description=cfg.get("description", ""),
                positive_keywords=[
                    str(k).lower().strip() for k in cfg.get("positive_keywords", [])
                ],
                service_indicators=[
                    str(k).lower().strip() for k in cfg.get("service_indicators", [])
                ],
                negative_keywords=[
                    str(k).lower().strip() for k in cfg.get("negative_keywords", [])
                ],
            )

    def _load_fallback_defaults(self) -> None:
        """In-memory fallback if config/niches.yaml is missing."""
        self.niches["personal_trainer"] = NicheDefinition(
            id="personal_trainer",
            name="Personal Trainer & Fitness Coach",
            description="Online fitness and hypertrophy coaches offering 1:1 training.",
            positive_keywords=[
                "fitness coach",
                "online coach",
                "personal trainer",
                "fat loss",
                "body transformation",
                "strength coach",
                "hypertrophy",
            ],
            service_indicators=[
                "1-on-1 coaching",
                "1:1 coaching",
                "apply below",
                "link in bio",
                "dm for coaching",
                "dm 'ready'",
                "client results",
                "custom workout",
            ],
            negative_keywords=[
                "gym clothing",
                "apparel",
                "activewear",
                "gymwear",
                "clothing brand",
                "supplements store",
                "shop now",
                "free shipping",
                "worldwide shipping",
            ],
        )

    def register_niche(self, definition: NicheDefinition) -> None:
        """Dynamically register or update a niche definition."""
        self.niches[definition.id] = definition

    def list_niches(self) -> list[str]:
        """Return all available niche IDs."""
        return list(self.niches.keys())

    def get_niche(self, niche_id: str) -> NicheDefinition | None:
        """Get the configuration for a specific niche."""
        return self.niches.get(niche_id)

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize profile text: lowercase, normalize whitespace, replace symbols."""
        if not text:
            return ""
        # Replace newlines, tabs, and excess spaces
        text = text.lower()
        text = re.sub(r"[\r\n\t]+", " ", text)
        return " " + " ".join(text.split()) + " "

    @classmethod
    def _find_keyword_matches(cls, normalized_text: str, keywords: list[str]) -> list[str]:
        """Find matching keywords or key phrases in normalized text."""
        matches: list[str] = []
        for kw in keywords:
            kw_clean = kw.strip().lower()
            if not kw_clean:
                continue

            # Word boundary regex or phrase substring matching
            # For multi-word phrases or special characters like '1:1', check direct substring
            pattern = rf"(?:\b|\s|^){re.escape(kw_clean)}(?:\b|\s|$)"
            if re.search(pattern, normalized_text) or kw_clean in normalized_text:
                matches.append(kw)
        return sorted(list(set(matches)))

    def evaluate(
        self,
        bio: str,
        full_name: str = "",
        username: str = "",
        external_url: str = "",
        niche_id: str = "personal_trainer",
    ) -> NicheVerdict:
        """Evaluate profile metadata against a specified niche.

        Classification Pipeline:
        1. Negative Filter: If any negative keyword matches (e.g. apparel, store), DISQUALIFY immediately.
        2. Positive Filter: Must match at least one domain positive keyword.
        3. Service Indicator Filter: Must match at least one service indicator (e.g. 1:1, apply below).
        """
        niche = self.niches.get(niche_id)
        if not niche:
            return NicheVerdict(
                niche=niche_id,
                is_match=False,
                confidence=0.0,
                matched_positives=[],
                matched_services=[],
                matched_negatives=[],
                disqualification_reason=f"Unknown niche '{niche_id}'. Available: {self.list_niches()}",
            )

        combined_text = f"{full_name} {username} {bio} {external_url}"
        normalized = self._normalize_text(combined_text)

        # 1. Negative Filter
        matched_negatives = self._find_keyword_matches(normalized, niche.negative_keywords)
        if matched_negatives:
            return NicheVerdict(
                niche=niche_id,
                is_match=False,
                confidence=0.0,
                matched_positives=[],
                matched_services=[],
                matched_negatives=matched_negatives,
                disqualification_reason=f"Matched negative keyword(s): {', '.join(matched_negatives)}",
            )

        # 2. Positive Keyword Filter
        matched_positives = self._find_keyword_matches(normalized, niche.positive_keywords)
        if not matched_positives:
            return NicheVerdict(
                niche=niche_id,
                is_match=False,
                confidence=0.0,
                matched_positives=[],
                matched_services=[],
                matched_negatives=[],
                disqualification_reason=f"No domain keywords matched for niche '{niche_id}'",
            )

        # 3. Service Indicator Filter
        matched_services = self._find_keyword_matches(normalized, niche.service_indicators)
        if not matched_services:
            return NicheVerdict(
                niche=niche_id,
                is_match=False,
                confidence=0.0,
                matched_positives=matched_positives,
                matched_services=[],
                matched_negatives=[],
                disqualification_reason="Missing high-ticket service indicators (e.g., '1-on-1 coaching', 'apply below')",
            )

        # 4. Compute Confidence Score
        # Base 0.50 + up to 0.25 from positive depth + up to 0.25 from service depth
        pos_boost = min(0.25, len(matched_positives) * 0.08)
        srv_boost = min(0.25, len(matched_services) * 0.08)
        confidence = round(min(1.0, 0.50 + pos_boost + srv_boost), 2)

        return NicheVerdict(
            niche=niche_id,
            is_match=True,
            confidence=confidence,
            matched_positives=matched_positives,
            matched_services=matched_services,
            matched_negatives=[],
            disqualification_reason=None,
        )
