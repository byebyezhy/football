"""Minimal PostgreSQL persistence for normalized, completed match results.

Database credentials are supplied by runtime environment variables, never by
public release archives. A real migration framework will follow in later PRs.
"""

from __future__ import annotations

from datetime import date
import os
from typing import Callable

from football_predictor.domain import MatchResult


SCHEMA_TABLE = """
CREATE TABLE IF NOT EXISTS match_results (
    id BIGSERIAL PRIMARY KEY,
    competition TEXT NOT NULL,
    season TEXT NOT NULL,
    played_on DATE NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_goals INTEGER NOT NULL CHECK (home_goals >= 0),
    away_goals INTEGER NOT NULL CHECK (away_goals >= 0),
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_match_fixture UNIQUE
      (competition, season, played_on, home_team, away_team),
    CONSTRAINT unique_source_identity UNIQUE
      (source, competition, season, source_id),
    CONSTRAINT different_teams CHECK (home_team <> away_team)
)
"""
SCHEMA_INDEX = """
CREATE INDEX IF NOT EXISTS match_results_competition_date_idx
    ON match_results (competition, played_on)
"""


class PostgresRepository:
    def __init__(self, *, connect: Callable | None = None) -> None:
        self._connect_override = connect

    def _connect(self):
        if self._connect_override is not None:
            return self._connect_override()
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("Install football-predictor[web] for PostgreSQL support") from exc
        return psycopg.connect(
            host=os.environ.get("DB_HOST", "db"),
            port=int(os.environ.get("DB_PORT", "5432")),
            dbname=os.environ.get("DB_NAME", "football"),
            user=os.environ.get("DB_USER", "football"),
            password=os.environ.get("DB_PASSWORD", ""),
            connect_timeout=5,
        )

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            # This string is static, never assembled from user input.
            connection.execute(SCHEMA_TABLE)
            connection.execute(SCHEMA_INDEX)

    def import_matches(self, matches: list[MatchResult]) -> int:
        """Import new fixtures, skipping duplicates without rewriting provenance."""
        statement = """
            INSERT INTO match_results
              (competition, season, played_on, home_team, away_team,
               home_goals, away_goals, source, source_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """
        inserted = 0
        with self._connect() as connection:
            with connection.cursor() as cursor:
                for match in matches:
                    cursor.execute(statement, (
                        match.competition, match.season, match.played_on,
                        match.home_team, match.away_team, match.home_goals,
                        match.away_goals, match.source, match.source_id,
                    ))
                    inserted += cursor.rowcount
        return inserted

    def status(self) -> dict:
        with self._connect() as connection:
            count, latest = connection.execute(
                "SELECT COUNT(*), MAX(played_on) FROM match_results"
            ).fetchone()
        return {
            "matches": count,
            "latest_match_date": latest.isoformat() if latest else None,
        }

    def competitions(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT competition FROM match_results ORDER BY competition"
            ).fetchall()
        return [row[0] for row in rows]

    def teams(self, competition: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT DISTINCT team FROM (
                       SELECT home_team AS team FROM match_results WHERE competition = %s
                       UNION
                       SELECT away_team AS team FROM match_results WHERE competition = %s
                   ) AS teams ORDER BY team""",
                (competition, competition),
            ).fetchall()
        return [row[0] for row in rows]

    def revision(self, competition: str, as_of: date) -> tuple[int, str]:
        with self._connect() as connection:
            count, updated = connection.execute(
                """SELECT COUNT(*), MAX(collected_at) FROM match_results
                   WHERE competition = %s AND played_on < %s""",
                (competition, as_of),
            ).fetchone()
        return count, updated.isoformat() if updated else ""

    def results(self, competition: str, as_of: date, *, limit: int = 3000) -> list[MatchResult]:
        """Only completed matches before the target date; cap training history."""
        if limit < 2 or limit > 10000:
            raise ValueError("Training limit out of range")
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT competition, season, played_on, home_team, away_team,
                          home_goals, away_goals, source, source_id
                   FROM match_results
                   WHERE competition = %s AND played_on < %s
                   ORDER BY played_on DESC, id DESC LIMIT %s""",
                (competition, as_of, limit),
            ).fetchall()
        return [MatchResult(*row) for row in reversed(rows)]
