"""Minimal PostgreSQL persistence for normalized, completed match results.

Database credentials are supplied by runtime environment variables, never by
public release archives. A real migration framework will follow in later PRs.
"""

from __future__ import annotations

from datetime import date, datetime
import json
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
SYNC_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS source_sync_runs (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    competition TEXT NOT NULL,
    season TEXT NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL CHECK (status IN ('ok', 'error')),
    fetched_count INTEGER NOT NULL CHECK (fetched_count >= 0),
    inserted_count INTEGER NOT NULL CHECK (inserted_count >= 0),
    invalid_count INTEGER NOT NULL CHECK (invalid_count >= 0),
    error_text TEXT
)
"""
SYNC_RUNS_INDEX = """
CREATE INDEX IF NOT EXISTS source_sync_runs_lookup_idx
    ON source_sync_runs (source, competition, season, finished_at DESC)
"""
BACKTEST_REPORTS_TABLE = """
CREATE TABLE IF NOT EXISTS model_backtest_reports (
    id BIGSERIAL PRIMARY KEY,
    competition TEXT NOT NULL,
    model TEXT NOT NULL,
    evaluate_from DATE NOT NULL,
    evaluate_through DATE NOT NULL,
    summary JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
BACKTEST_REPORTS_INDEX = """
CREATE INDEX IF NOT EXISTS model_backtest_reports_lookup_idx
    ON model_backtest_reports (competition, model, generated_at DESC)
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
            connection.execute(SYNC_RUNS_TABLE)
            connection.execute(SYNC_RUNS_INDEX)
            connection.execute(BACKTEST_REPORTS_TABLE)
            connection.execute(BACKTEST_REPORTS_INDEX)

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

    def last_successful_sync(self, source: str, competition: str, season: str) -> datetime | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT MAX(finished_at) FROM source_sync_runs
                   WHERE source = %s AND competition = %s AND season = %s AND status = 'ok'""",
                (source, competition, season),
            ).fetchone()
        return row[0] if row else None

    def record_source_sync(self, *, source: str, competition: str, season: str,
                           status: str, fetched: int, inserted: int,
                           invalid: int, error: str | None = None) -> None:
        if status not in {"ok", "error"}:
            raise ValueError("Unknown source sync status")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO source_sync_runs
                   (source, competition, season, status, fetched_count,
                    inserted_count, invalid_count, error_text)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (source, competition, season, status, fetched, inserted, invalid,
                 error[:500] if error else None),
            )

    def source_sync_status(self, competition: str, *, limit: int = 10) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT DISTINCT ON (source, season)
                       source, season, status, fetched_count, inserted_count,
                       invalid_count, finished_at
                   FROM source_sync_runs WHERE competition = %s
                   ORDER BY source, season, finished_at DESC, id DESC""",
                (competition,),
            ).fetchall()
        rows = sorted(rows, key=lambda row: row[6], reverse=True)[:limit]
        return [{"source": row[0], "season": row[1], "status": row[2],
                 "fetched": row[3], "inserted": row[4], "invalid": row[5],
                 "finished_at": row[6].isoformat()} for row in rows]

    def save_backtest_report(self, competition: str, model: str,
                             evaluate_from: date, evaluate_through: date,
                             summary: dict) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO model_backtest_reports
                   (competition, model, evaluate_from, evaluate_through, summary)
                   VALUES (%s, %s, %s, %s, %s::jsonb)""",
                (competition, model, evaluate_from, evaluate_through,
                 json.dumps(summary, allow_nan=False)),
            )

    def recent_backtests(self, competition: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT DISTINCT ON (model)
                       model, evaluate_from, evaluate_through, summary, generated_at
                   FROM model_backtest_reports WHERE competition = %s
                   ORDER BY model, generated_at DESC, id DESC""",
                (competition,),
            ).fetchall()
        return [{"model": row[0], "evaluate_from": row[1].isoformat(),
                 "evaluate_through": row[2].isoformat(),
                 "summary": json.loads(row[3]) if isinstance(row[3], str) else row[3],
                 "generated_at": row[4].isoformat()} for row in rows]

    def last_backtest_at(self, competition: str) -> datetime | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT MAX(generated_at) FROM model_backtest_reports WHERE competition = %s",
                (competition,),
            ).fetchone()
        return row[0] if row else None
