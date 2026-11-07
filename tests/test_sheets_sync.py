"""Unit tests for the deduplicating, non-destructive CRM sync engine."""

import csv
from collections.abc import Generator
from pathlib import Path

import pytest

from src.sheets_sync import (
    DISPOSED_HEADERS,
    TRACKER_HEADERS,
    LocalSheetsSync,
)


@pytest.fixture
def temp_crm(tmp_path: Path) -> Generator[LocalSheetsSync, None, None]:
    """Create a temporary LocalSheetsSync CRM instance."""
    crm_dir = tmp_path / "crm_test"
    crm = LocalSheetsSync(data_dir=crm_dir)
    yield crm


class TestColumnSchemas:
    """Verify exact column ordering and naming for Tracker and Disposed tabs."""

    def test_tracker_headers(self, temp_crm: LocalSheetsSync) -> None:
        assert TRACKER_HEADERS == [
            "Username",
            "AHS",
            "Outreach Date",
            "Status",
            "Days Since Outreach",
            "Notes",
        ]
        with open(temp_crm.tracker_file, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)
            assert headers == TRACKER_HEADERS

    def test_disposed_headers(self, temp_crm: LocalSheetsSync) -> None:
        assert DISPOSED_HEADERS == [
            "Username",
            "Followers",
            "Reason",
            "Disposed Date",
            "Notes",
        ]
        with open(temp_crm.disposed_file, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)
            assert headers == DISPOSED_HEADERS


class TestDeduplicationPreCheck:
    """Ensure handles in either Tracker or Disposed are immediately identified and skipped."""

    def test_dedup_in_tracker(self, temp_crm: LocalSheetsSync) -> None:
        temp_crm.append_to_tracker("coach_steve", 74.5)

        # Exact match
        assert temp_crm.is_existing("coach_steve") is True
        # Handle with @ prefix
        assert temp_crm.is_existing("@coach_steve") is True
        # Case insensitive match
        assert temp_crm.is_existing("COACH_STEVE") is True
        # New unseen handle
        assert temp_crm.is_existing("unseen_trainer") is False

    def test_dedup_in_disposed(self, temp_crm: LocalSheetsSync) -> None:
        temp_crm.append_to_disposed("disqualified_brand", 250000, "Followers > 100k")

        assert temp_crm.is_existing("disqualified_brand") is True
        assert temp_crm.is_existing("@disqualified_brand") is True
        assert temp_crm.is_existing("DISQUALIFIED_BRAND") is True
        assert temp_crm.is_existing("fresh_candidate") is False

    def test_cache_reload_from_disk(self, tmp_path: Path) -> None:
        crm_dir = tmp_path / "crm_reload"
        crm1 = LocalSheetsSync(data_dir=crm_dir)
        crm1.append_to_tracker("lead_alpha", 82.0)
        crm1.append_to_disposed("dead_account_beta", 0, "404 Not Found")

        # Create new instance pointing to same files
        crm2 = LocalSheetsSync(data_dir=crm_dir)
        assert crm2.is_existing("lead_alpha") is True
        assert crm2.is_existing("dead_account_beta") is True
        assert crm2.get_tracker_count() == 1
        assert crm2.get_disposed_count() == 1


class TestNonDestructiveAppending:
    """Verify that new appends never overwrite existing rows and index correctly."""

    def test_sequential_appending(self, temp_crm: LocalSheetsSync) -> None:
        # Header is row 1
        row_idx1 = temp_crm.append_to_tracker("lead_1", 65.0)
        assert row_idx1 == 2  # Row 2

        row_idx2 = temp_crm.append_to_tracker("lead_2", 78.5)
        assert row_idx2 == 3  # Row 3

        row_idx3 = temp_crm.append_to_tracker("lead_3", 88.0)
        assert row_idx3 == 4  # Row 4

        # Read back all rows
        with open(temp_crm.tracker_file, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        assert len(rows) == 4  # 1 header + 3 leads
        assert rows[1][0] == "lead_1"
        assert rows[1][1] == "65.0"
        assert rows[1][3] == "new lead"
        assert rows[1][5] == "https://www.instagram.com/lead_1/"

        assert rows[2][0] == "lead_2"
        assert rows[3][0] == "lead_3"

    def test_disposed_record_formatting(self, temp_crm: LocalSheetsSync) -> None:
        row_idx = temp_crm.append_to_disposed(
            "gym_apparel_store", 45000, "Matched negative: apparel"
        )
        assert row_idx == 2

        with open(temp_crm.disposed_file, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        assert len(rows) == 2
        disposed_row = rows[1]
        assert disposed_row[0] == "gym_apparel_store"
        assert disposed_row[1] == "45,000"
        assert disposed_row[2] == "Matched negative: apparel"
        assert disposed_row[4] == "https://www.instagram.com/gym_apparel_store/"


class TestBatchQuotaLoop:
    """Simulate a hunt run until target quota is reached."""

    def test_quota_loop_execution(self, temp_crm: LocalSheetsSync) -> None:
        target_quota = 5
        candidates = [
            ("coach_1", True, 75.0, 15000, ""),
            ("brand_2", False, 0.0, 120000, "Followers > 100k"),
            ("coach_1", True, 75.0, 15000, ""),  # duplicate, must be skipped
            ("coach_3", True, 68.0, 8000, ""),
            ("dead_4", False, 0.0, 0, "404 Not Found"),
            ("coach_5", True, 62.0, 22000, ""),
            ("coach_6", True, 85.0, 5000, ""),
            ("coach_7", True, 91.0, 31000, ""),  # 5th qualified lead
            ("coach_8", True, 70.0, 10000, ""),  # extra
        ]

        new_leads_added = 0
        skipped_duplicates = 0
        disposed_added = 0

        for username, is_qualified, ahs, followers, reason in candidates:
            # Step 1: Pre-check deduplication
            if temp_crm.is_existing(username):
                skipped_duplicates += 1
                continue

            # Step 2: Route qualified vs disposed
            if is_qualified:
                temp_crm.append_to_tracker(username, ahs)
                new_leads_added += 1
            else:
                temp_crm.append_to_disposed(username, followers, reason)
                disposed_added += 1

            if new_leads_added >= target_quota:
                break

        assert new_leads_added == 5
        assert skipped_duplicates == 1
        assert disposed_added == 2
        assert temp_crm.get_tracker_count() == 5
        assert temp_crm.get_disposed_count() == 2


class TestCRMFactory:
    """Test get_crm_backend factory logic."""

    def test_factory_returns_local_when_forced(self, tmp_path: Path) -> None:
        from src.sheets_sync import get_crm_backend

        crm = get_crm_backend(force_local=True, local_dir=tmp_path / "factory_local")
        assert isinstance(crm, LocalSheetsSync)

    def test_factory_fallback_when_creds_missing(self, tmp_path: Path) -> None:
        from src.sheets_sync import get_crm_backend

        crm = get_crm_backend(
            force_local=False,
            local_dir=tmp_path / "factory_fallback",
            service_account_path="nonexistent_service_account.json",
        )
        assert isinstance(crm, LocalSheetsSync)


class TestMockedGoogleSheetsCRM:
    """Test GoogleSheetsCRM logic with mocked gspread objects."""

    def test_google_sheets_crm_operations(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from unittest.mock import MagicMock

        from src.sheets_sync import GoogleSheetsCRM

        # Create dummy creds file
        dummy_creds = tmp_path / "service_account.json"
        dummy_creds.write_text('{"type": "service_account"}', encoding="utf-8")

        mock_tracker_ws = MagicMock()
        mock_tracker_ws.row_values.return_value = ["Username", "AHS"]
        mock_tracker_ws.col_values.return_value = ["Username", "existing_tracker_user"]

        mock_disposed_ws = MagicMock()
        mock_disposed_ws.row_values.return_value = ["Username", "Followers"]
        mock_disposed_ws.col_values.return_value = ["Username", "existing_disposed_user"]

        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheet.side_effect = lambda title: (
            mock_tracker_ws if title == "Tracker" else mock_disposed_ws
        )

        mock_gc = MagicMock()
        mock_gc.open_by_key.return_value = mock_spreadsheet
        mock_gc.open.return_value = mock_spreadsheet

        monkeypatch.setattr(
            "google.oauth2.service_account.Credentials.from_service_account_file",
            lambda path, scopes: MagicMock(),
        )
        monkeypatch.setattr("gspread.authorize", lambda creds: mock_gc)

        crm = GoogleSheetsCRM(
            service_account_path=str(dummy_creds),
            sheet_id="dummy_sheet_id",
        )

        assert crm.is_existing("existing_tracker_user") is True
        assert crm.is_existing("existing_disposed_user") is True
        assert crm.is_existing("brand_new_lead") is False

        # Test append to tracker
        row_idx = crm.append_to_tracker("brand_new_lead", 82.5)
        assert row_idx == 3
        mock_tracker_ws.append_row.assert_called_once()
        assert crm.is_existing("brand_new_lead") is True

        # Test append to disposed
        disp_idx = crm.append_to_disposed("brand_disposed", 150000, "Followers > 100k")
        assert disp_idx == 3
        mock_disposed_ws.append_row.assert_called_once()
        assert crm.is_existing("brand_disposed") is True
