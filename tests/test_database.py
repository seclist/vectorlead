"""Unit tests for the SQLite local prospect cache and history database."""

from pathlib import Path

import pytest

from src.database import ProspectDatabase


@pytest.fixture
def temp_db(tmp_path: Path) -> ProspectDatabase:
    """Create a temporary SQLite database."""
    db_file = tmp_path / "test_prospects.db"
    return ProspectDatabase(db_path=db_file)


class TestProspectDatabase:
    """Test CRUD operations, deduplication, and stat counters in SQLite."""

    def test_upsert_and_retrieve(self, temp_db: ProspectDatabase) -> None:
        temp_db.upsert_prospect(
            username="coach_alex",
            full_name="Alex Turner",
            followers=12500,
            bio="Online Coach | Apply below",
            niche="personal_trainer",
            niche_match=True,
            base_ahs=62.0,
            multiplier=1.2,
            final_ahs=74.4,
            status="qualified",
        )

        assert temp_db.is_evaluated("coach_alex") is True
        assert temp_db.is_evaluated("@coach_alex") is True
        assert temp_db.is_evaluated("COACH_ALEX") is True
        assert temp_db.is_evaluated("unseen_user") is False

        p = temp_db.get_prospect("coach_alex")
        assert p is not None
        assert p["username"] == "coach_alex"
        assert p["followers"] == 12500
        assert p["final_ahs"] == 74.4
        assert p["status"] == "qualified"

    def test_mark_crm_synced(self, temp_db: ProspectDatabase) -> None:
        temp_db.upsert_prospect(username="lead_sync", status="qualified", crm_synced=False)
        p = temp_db.get_prospect("lead_sync")
        assert p is not None
        assert p["crm_synced"] == 0

        temp_db.mark_crm_synced("lead_sync")
        p_updated = temp_db.get_prospect("lead_sync")
        assert p_updated is not None
        assert p_updated["crm_synced"] == 1

    def test_stats_aggregation(self, temp_db: ProspectDatabase) -> None:
        temp_db.upsert_prospect(username="qual_1", status="qualified", crm_synced=True)
        temp_db.upsert_prospect(username="qual_2", status="qualified", crm_synced=True)
        temp_db.upsert_prospect(username="disp_1", status="disposed", crm_synced=True)

        stats = temp_db.get_stats()
        assert stats["total"] == 3
        assert stats["qualified"] == 2
        assert stats["disposed"] == 1
        assert stats["synced"] == 3

    def test_list_prospects_filtering(self, temp_db: ProspectDatabase) -> None:
        temp_db.upsert_prospect(
            username="fit_coach", niche="personal_trainer", status="qualified", final_ahs=85.0
        )
        temp_db.upsert_prospect(
            username="realtor_mike", niche="realtor", status="qualified", final_ahs=75.0
        )
        temp_db.upsert_prospect(
            username="fit_brand", niche="personal_trainer", status="disposed", final_ahs=0.0
        )

        all_prospects = temp_db.list_prospects()
        assert len(all_prospects) == 3

        trainer_only = temp_db.list_prospects(niche="personal_trainer")
        assert len(trainer_only) == 2

        qualified_trainers = temp_db.list_prospects(status="qualified", niche="personal_trainer")
        assert len(qualified_trainers) == 1
        assert qualified_trainers[0]["username"] == "fit_coach"
