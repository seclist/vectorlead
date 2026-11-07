# 📋 Changelog

All notable changes to **VectorLead** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.0] - 2026-11-07

### Added
- **Project Rebranding:** Officially transitioned to **VectorLead**.
- **Engagement Quality Score (EQS):** Comment-to-like ratio analysis and creator reply velocity detection to filter bot engagement pods.
- **Funnel Maturity Index (FMI):** Bio link classification (Calendly, Typeform, Skool, Kajabi, Stan Store) and automated ManyChat keyword trigger detection (`"Comment 'READY'"`).
- **Follower Churn Filter ($F_{\text{ratio}}$):** Direct disqualification of mass-follow/unfollow churn bots.
- **Half-Life Exponential Recency Decay:** Post consistency weighting with $\lambda = 7$ day half-life replacing flat 30-day post counts.
- **Velocity Acceleration ($\Delta R_v$):** Second derivative detection of viral breakout creators with automatic $+10\%$ momentum boost and `Breakout 🚀` badge.
- **Official Visual Branding Assets:** Added clean, developer-grade geometric vector logo and GitHub repository banner (`assets/`).
- **Comprehensive GitHub Community Templates:** Issue forms (`bug_report`, `feature_request`, `niche_proposal`), PR template, and security guidelines.

### Changed
- Refactored `AccountMetrics` and `AHSResult` to include full vector breakdown metrics.
- Upgraded SQLite database schema with automatic schema migration for `f_ratio`, `funnel_tier`, `is_breakout`, and `eqs_score`.
- Enhanced CLI tables with cyber aesthetics, tier badges, and breakout indicators.

---

## [0.1.0] - 2026-11-07

### Added
- Initial release of core Instagram Lead Discovery Engine.
- Rolling 35-day Account Health Score (AHS) mathematical formula ($S_G, S_V, S_C, S_P$).
- Zero-login crawler verification via `facebookexternalhit/1.1`.
- Modular YAML niche filtering engine (`config/niches.yaml`).
- Non-destructive Google Sheets & Local CSV CRM pipeline with $O(1)$ deduplication.
- Rich terminal CLI interface (`hunt`, `test-account`, `stats`, `list-niches`).
