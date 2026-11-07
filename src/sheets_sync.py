"""Deduplicating, Non-Destructive CRM Sync Engine for Google Sheets and Local Fallback.

Maintains two synchronized worksheets:
1. 'Tracker': High-velocity qualified leads (AHS >= 60.0).
2. 'Disposed': Disqualified profiles (over 100k, outside niche, dead 404, AHS < 60).

Enforces strict deduplication pre-checks across both tabs and guarantees
non-destructive appending from the first dynamically located empty row.
"""

from __future__ import annotations

import csv
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

TRACKER_HEADERS = [
    "Username",
    "AHS",
    "Outreach Date",
    "Status",
    "Days Since Outreach",
    "Notes",
]

DISPOSED_HEADERS = [
    "Username",
    "Followers",
    "Reason",
    "Disposed Date",
    "Notes",
]


class BaseCRM(ABC):
    """Abstract CRM interface for deduplication, routing, and non-destructive appending."""

    @abstractmethod
    def is_existing(self, username: str) -> bool:
        """Check if username exists in either Tracker or Disposed tabs."""
        pass

    @abstractmethod
    def append_to_tracker(self, username: str, ahs: float) -> int:
        """Append qualified lead to Tracker worksheet. Returns row index."""
        pass

    @abstractmethod
    def append_to_disposed(self, username: str, followers: Any, reason: str) -> int:
        """Append disqualified candidate to Disposed worksheet. Returns row index."""
        pass

    @abstractmethod
    def get_tracker_count(self) -> int:
        """Return total leads currently in Tracker tab."""
        pass

    @abstractmethod
    def get_disposed_count(self) -> int:
        """Return total entries currently in Disposed tab."""
        pass

    @staticmethod
    def clean_handle(username: str) -> str:
        """Strip @ prefix, whitespace, and convert to lowercase."""
        return username.lstrip("@").strip().lower()


class LocalSheetsSync(BaseCRM):
    """File-backed local CRM mirror (CSV) with identical deduplication and non-destructive rules."""

    def __init__(self, data_dir: Optional[Path | str] = None) -> None:
        self.data_dir = Path(data_dir or "crm_data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.tracker_file = self.data_dir / "Tracker.csv"
        self.disposed_file = self.data_dir / "Disposed.csv"

        self.existing_usernames: set[str] = set()
        self._init_files()
        self.refresh_cache()

    def _init_files(self) -> None:
        """Create CSV files with canonical headers if not present."""
        if not self.tracker_file.exists():
            with open(self.tracker_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(TRACKER_HEADERS)

        if not self.disposed_file.exists():
            with open(self.disposed_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(DISPOSED_HEADERS)

    def refresh_cache(self) -> set[str]:
        """Read column 0 (Username) from both Tracker and Disposed CSVs."""
        self.existing_usernames.clear()

        for file_path in [self.tracker_file, self.disposed_file]:
            if file_path.exists():
                with open(file_path, "r", newline="", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    try:
                        header = next(reader, None)
                    except StopIteration:
                        header = None

                    for row in reader:
                        if row and row[0]:
                            self.existing_usernames.add(self.clean_handle(row[0]))

        return self.existing_usernames

    def is_existing(self, username: str) -> bool:
        """Pre-check against in-memory cached handles."""
        return self.clean_handle(username) in self.existing_usernames

    def append_to_tracker(self, username: str, ahs: float) -> int:
        """Append to Tracker tab without overwriting.

        Schema:
        1. Username
        2. AHS
        3. Outreach Date ("")
        4. Status ("new lead")
        5. Days Since Outreach ("")
        6. Notes (clickable link)
        """
        clean_user = self.clean_handle(username)
        link = f"https://www.instagram.com/{clean_user}/"
        row_data = [clean_user, f"{ahs:.1f}", "", "new lead", "", link]

        # Calculate next empty row index (1-based index)
        with open(self.tracker_file, "r", newline="", encoding="utf-8") as f:
            total_rows = sum(1 for _ in f)
        target_row_idx = total_rows + 1

        with open(self.tracker_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(row_data)

        self.existing_usernames.add(clean_user)
        logger.info("Appended @%s to Tracker at row %d", clean_user, target_row_idx)
        return target_row_idx

    def append_to_disposed(self, username: str, followers: Any, reason: str) -> int:
        """Append to Disposed tab without overwriting."""
        clean_user = self.clean_handle(username)
        link = f"https://www.instagram.com/{clean_user}/"
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        followers_str = f"{followers:,}" if isinstance(followers, int) else str(followers)
        row_data = [clean_user, followers_str, reason, date_str, link]

        with open(self.disposed_file, "r", newline="", encoding="utf-8") as f:
            total_rows = sum(1 for _ in f)
        target_row_idx = total_rows + 1

        with open(self.disposed_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(row_data)

        self.existing_usernames.add(clean_user)
        logger.info("Appended @%s to Disposed at row %d (Reason: %s)", clean_user, target_row_idx, reason)
        return target_row_idx

    def get_tracker_count(self) -> int:
        with open(self.tracker_file, "r", newline="", encoding="utf-8") as f:
            count = sum(1 for _ in f)
        return max(0, count - 1)

    def get_disposed_count(self) -> int:
        with open(self.disposed_file, "r", newline="", encoding="utf-8") as f:
            count = sum(1 for _ in f)
        return max(0, count - 1)


class GoogleSheetsCRM(BaseCRM):
    """Production Google Sheets CRM connecting via gspread and service account credentials."""

    def __init__(
        self,
        service_account_path: Optional[str] = None,
        sheet_id: Optional[str] = None,
        sheet_name: Optional[str] = None,
    ) -> None:
        import gspread
        from google.oauth2.service_account import Credentials

        self.creds_path = (
            service_account_path
            or os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH")
            or "service_account.json"
        )
        self.sheet_id = sheet_id or os.getenv("GOOGLE_SHEET_ID")
        self.sheet_name = sheet_name or os.getenv("GOOGLE_SHEET_NAME", "InstaPulse Lead Tracker")

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        if not Path(self.creds_path).exists():
            raise FileNotFoundError(
                f"Google Service Account keyfile not found at: {self.creds_path}"
            )

        creds = Credentials.from_service_account_file(self.creds_path, scopes=scopes)
        self.gc = gspread.authorize(creds)

        # Open workbook by key or title
        if self.sheet_id and self.sheet_id != "your_google_sheet_id_here":
            self.spreadsheet = self.gc.open_by_key(self.sheet_id)
        else:
            self.spreadsheet = self.gc.open(self.sheet_name)

        # Ensure tabs exist and initialize headers if empty
        self.tracker_ws = self._get_or_create_worksheet("Tracker", TRACKER_HEADERS)
        self.disposed_ws = self._get_or_create_worksheet("Disposed", DISPOSED_HEADERS)

        self.existing_usernames: set[str] = set()
        self.refresh_cache()

    def _get_or_create_worksheet(self, title: str, headers: list[str]) -> Any:
        """Retrieve existing worksheet or create it with canonical header row."""
        try:
            ws = self.spreadsheet.worksheet(title)
        except Exception:
            ws = self.spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers) + 2)

        # Check if header row exists
        first_row = ws.row_values(1)
        if not first_row:
            ws.append_row(headers, value_input_option="USER_ENTERED")

        return ws

    def refresh_cache(self) -> set[str]:
        """Fetch all usernames from column 1 of Tracker and Disposed worksheets."""
        self.existing_usernames.clear()

        # Fetch Tracker column 1
        try:
            tracker_users = self.tracker_ws.col_values(1)
            for user in tracker_users[1:]:  # skip header
                if user:
                    self.existing_usernames.add(self.clean_handle(user))
        except Exception as e:
            logger.warning("Failed to read Tracker col_values: %s", e)

        # Fetch Disposed column 1
        try:
            disposed_users = self.disposed_ws.col_values(1)
            for user in disposed_users[1:]:  # skip header
                if user:
                    self.existing_usernames.add(self.clean_handle(user))
        except Exception as e:
            logger.warning("Failed to read Disposed col_values: %s", e)

        return self.existing_usernames

    def is_existing(self, username: str) -> bool:
        """Pre-check against cached handles in both sheets."""
        return self.clean_handle(username) in self.existing_usernames

    def append_to_tracker(self, username: str, ahs: float) -> int:
        """Dynamically locate first empty row and append without overwriting."""
        clean_user = self.clean_handle(username)
        link = f"https://www.instagram.com/{clean_user}/"
        row_data = [clean_user, f"{ahs:.1f}", "", "new lead", "", link]

        # Locate next empty row index
        col1_vals = self.tracker_ws.col_values(1)
        next_empty_row = len(col1_vals) + 1

        self.tracker_ws.append_row(row_data, value_input_option="USER_ENTERED")
        self.existing_usernames.add(clean_user)
        logger.info("Appended @%s to Google Sheets Tracker at row %d", clean_user, next_empty_row)
        return next_empty_row

    def append_to_disposed(self, username: str, followers: Any, reason: str) -> int:
        """Append to Disposed tab at next available row."""
        clean_user = self.clean_handle(username)
        link = f"https://www.instagram.com/{clean_user}/"
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        followers_str = f"{followers:,}" if isinstance(followers, int) else str(followers)
        row_data = [clean_user, followers_str, reason, date_str, link]

        col1_vals = self.disposed_ws.col_values(1)
        next_empty_row = len(col1_vals) + 1

        self.disposed_ws.append_row(row_data, value_input_option="USER_ENTERED")
        self.existing_usernames.add(clean_user)
        logger.info("Appended @%s to Google Sheets Disposed at row %d", clean_user, next_empty_row)
        return next_empty_row

    def get_tracker_count(self) -> int:
        return max(0, len(self.tracker_ws.col_values(1)) - 1)

    def get_disposed_count(self) -> int:
        return max(0, len(self.disposed_ws.col_values(1)) - 1)


def get_crm_backend(
    force_local: bool = False,
    local_dir: Optional[Path | str] = None,
    service_account_path: Optional[str] = None,
    sheet_id: Optional[str] = None,
) -> BaseCRM:
    """Factory creating GoogleSheetsCRM if credentials exist, falling back to LocalSheetsSync."""
    if force_local:
        return LocalSheetsSync(data_dir=local_dir)

    creds_path = (
        service_account_path
        or os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH")
        or "service_account.json"
    )

    if Path(creds_path).exists():
        try:
            return GoogleSheetsCRM(
                service_account_path=creds_path,
                sheet_id=sheet_id,
            )
        except Exception as e:
            logger.warning(
                "Could not connect to Google Sheets (%s). Falling back to LocalSheetsSync.",
                e,
            )
            return LocalSheetsSync(data_dir=local_dir)

    return LocalSheetsSync(data_dir=local_dir)
