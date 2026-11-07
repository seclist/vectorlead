"""Local SQLite Prospect Cache and History Database.

Prevents duplicate crawls, stores historical AHS momentum scores, and logs
qualification verdicts locally for fast offline queries and syncing.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional


class ProspectDatabase:
    """SQLite manager for caching Instagram prospects and qualification outcomes."""

    DEFAULT_DB_PATH = Path("vectorlead.db")

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self.db_path = Path(db_path) if db_path else self.DEFAULT_DB_PATH
        self.init_db()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        """Create database tables and indexes if they do not exist."""
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prospects (
                    username TEXT PRIMARY KEY,
                    full_name TEXT,
                    followers INTEGER DEFAULT 0,
                    following INTEGER DEFAULT 0,
                    posts_count INTEGER DEFAULT 0,
                    bio TEXT,
                    niche TEXT,
                    niche_match INTEGER DEFAULT 0,
                    base_ahs REAL DEFAULT 0.0,
                    multiplier REAL DEFAULT 0.0,
                    final_ahs REAL DEFAULT 0.0,
                    f_ratio REAL DEFAULT 1.0,
                    funnel_tier TEXT DEFAULT 'high_ticket',
                    is_breakout INTEGER DEFAULT 0,
                    eqs_score REAL DEFAULT 50.0,
                    status TEXT NOT NULL,           -- 'qualified' or 'disposed'
                    disposal_reason TEXT,
                    crm_synced INTEGER DEFAULT 0,   -- 1 if pushed to Sheets Tracker/Disposed
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # Automatic schema migration for existing databases
            existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(prospects)").fetchall()}
            for col, col_type in [
                ("f_ratio", "REAL DEFAULT 1.0"),
                ("funnel_tier", "TEXT DEFAULT 'high_ticket'"),
                ("is_breakout", "INTEGER DEFAULT 0"),
                ("eqs_score", "REAL DEFAULT 50.0"),
            ]:
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE prospects ADD COLUMN {col} {col_type}")

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_prospects_status ON prospects(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_prospects_niche ON prospects(niche)"
            )

    def upsert_prospect(
        self,
        username: str,
        full_name: str = "",
        followers: int = 0,
        following: int = 0,
        posts_count: int = 0,
        bio: str = "",
        niche: str = "",
        niche_match: bool = False,
        base_ahs: float = 0.0,
        multiplier: float = 0.0,
        final_ahs: float = 0.0,
        f_ratio: float = 1.0,
        funnel_tier: str = "high_ticket",
        is_breakout: bool = False,
        eqs_score: float = 50.0,
        status: str = "disposed",
        disposal_reason: Optional[str] = None,
        crm_synced: bool = False,
    ) -> None:
        """Insert or update a prospect in the local database."""
        clean_user = username.lstrip("@").strip().lower()
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO prospects (
                    username, full_name, followers, following, posts_count,
                    bio, niche, niche_match, base_ahs, multiplier, final_ahs,
                    f_ratio, funnel_tier, is_breakout, eqs_score,
                    status, disposal_reason, crm_synced, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    full_name = excluded.full_name,
                    followers = excluded.followers,
                    following = excluded.following,
                    posts_count = excluded.posts_count,
                    bio = excluded.bio,
                    niche = excluded.niche,
                    niche_match = excluded.niche_match,
                    base_ahs = excluded.base_ahs,
                    multiplier = excluded.multiplier,
                    final_ahs = excluded.final_ahs,
                    f_ratio = excluded.f_ratio,
                    funnel_tier = excluded.funnel_tier,
                    is_breakout = excluded.is_breakout,
                    eqs_score = excluded.eqs_score,
                    status = excluded.status,
                    disposal_reason = excluded.disposal_reason,
                    crm_synced = CASE WHEN excluded.crm_synced = 1 THEN 1 ELSE prospects.crm_synced END,
                    updated_at = excluded.updated_at
                """,
                (
                    clean_user,
                    full_name,
                    followers,
                    following,
                    posts_count,
                    bio,
                    niche,
                    1 if niche_match else 0,
                    base_ahs,
                    multiplier,
                    final_ahs,
                    f_ratio,
                    funnel_tier,
                    1 if is_breakout else 0,
                    eqs_score,
                    status,
                    disposal_reason,
                    1 if crm_synced else 0,
                    now_iso,
                    now_iso,
                ),
            )

    def get_prospect(self, username: str) -> Optional[dict[str, Any]]:
        """Retrieve prospect details by username."""
        clean_user = username.lstrip("@").strip().lower()
        with self._connection() as conn:
            cur = conn.execute(
                "SELECT * FROM prospects WHERE username = ?", (clean_user,)
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def is_evaluated(self, username: str) -> bool:
        """Check if a handle has already been evaluated."""
        clean_user = username.lstrip("@").strip().lower()
        with self._connection() as conn:
            cur = conn.execute(
                "SELECT 1 FROM prospects WHERE username = ?", (clean_user,)
            )
            return cur.fetchone() is not None

    def mark_crm_synced(self, username: str) -> None:
        """Mark a prospect as synced with the CRM sheets."""
        clean_user = username.lstrip("@").strip().lower()
        with self._connection() as conn:
            conn.execute(
                "UPDATE prospects SET crm_synced = 1, updated_at = ? WHERE username = ?",
                (datetime.now(timezone.utc).isoformat(), clean_user),
            )

    def get_stats(self) -> dict[str, int]:
        """Return total counts of evaluated, qualified, disposed, and synced prospects."""
        with self._connection() as conn:
            cur = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'qualified' THEN 1 ELSE 0 END) as qualified,
                    SUM(CASE WHEN status = 'disposed' THEN 1 ELSE 0 END) as disposed,
                    SUM(CASE WHEN crm_synced = 1 THEN 1 ELSE 0 END) as synced
                FROM prospects
                """
            )
            row = cur.fetchone()
            if not row:
                return {"total": 0, "qualified": 0, "disposed": 0, "synced": 0}
            return {
                "total": row["total"] or 0,
                "qualified": row["qualified"] or 0,
                "disposed": row["disposed"] or 0,
                "synced": row["synced"] or 0,
            }

    def list_prospects(
        self, status: Optional[str] = None, niche: Optional[str] = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List prospects with optional status and niche filters."""
        query = "SELECT * FROM prospects WHERE 1=1"
        params: list[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if niche:
            query += " AND niche = ?"
            params.append(niche)

        query += " ORDER BY final_ahs DESC, updated_at DESC LIMIT ?"
        params.append(limit)

        with self._connection() as conn:
            cur = conn.execute(query, tuple(params))
            return [dict(r) for r in cur.fetchall()]
