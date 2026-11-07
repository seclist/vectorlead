"""VectorLead: Autonomous Instagram Lead Discovery, Qualification, and CRM Sync Engine.

This package provides an algorithmic momentum engine (Account Health Score - AHS)
enhanced with Engagement Quality Scoring (EQS), Funnel Maturity Index (FMI),
half-life post recency decay, zero-login crawler verification, modular niche filters,
and a non-destructive Google Sheets CRM sync pipeline.
"""

__version__ = "0.2.0"
__all__ = [
    "calculate_ahs",
    "calculate_dynamic_multiplier",
    "AccountMetrics",
    "AHSResult",
    "ComponentScores",
    "FunnelTier",
    "InstagramCrawler",
    "InstagramProfile",
    "NicheClassifier",
    "ProspectDatabase",
    "GoogleSheetsCRM",
    "LocalSheetsSync",
]

from src.algorithm import (
    AccountMetrics,
    AHSResult,
    ComponentScores,
    FunnelTier,
    calculate_ahs,
    calculate_dynamic_multiplier,
)
from src.classifier import NicheClassifier
from src.database import ProspectDatabase
from src.scraper import InstagramCrawler, InstagramProfile
from src.sheets_sync import GoogleSheetsCRM, LocalSheetsSync
