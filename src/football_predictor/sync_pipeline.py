"""Idempotent scheduled harvesting from replaceable historical-results plugins."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable

from football_predictor.domain import FetchContext
from football_predictor.sources.base import RESULTS
from football_predictor.sources.soccerdata_history import SoccerdataMatchHistory


@dataclass(frozen=True)
class SyncOutcome:
    competition: str
    season: str
    status: str
    fetched: int = 0
    inserted: int = 0
    invalid: int = 0


def season_keys(as_of: date, *, completed_seasons: int = 5) -> list[str]:
    """Five completed European seasons plus the current season (July boundary)."""
    if not 1 <= completed_seasons <= 10:
        raise ValueError("completed_seasons must be between 1 and 10")
    start_year = as_of.year if as_of.month >= 7 else as_of.year - 1
    return [f"{year}-{(year + 1) % 100:02d}"
            for year in range(start_year - completed_seasons, start_year + 1)]


def sync_competition(
    repository,
    competition: str,
    *,
    as_of: date,
    now: datetime,
    source_factory: Callable[[bool], object] | None = None,
    completed_seasons: int = 5,
) -> list[SyncOutcome]:
    """Fetch each season separately; one broken season cannot stop another.

    Archived seasons are rechecked monthly, while current-season results use
    a fresh network response once a day. Only successful fetches set freshness.
    Historical results remain in PostgreSQL even when this job is unavailable.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if source_factory is None:
        source_factory = lambda no_cache: SoccerdataMatchHistory(no_cache=no_cache)

    seasons = season_keys(as_of, completed_seasons=completed_seasons)
    context_time = datetime.combine(as_of, time.min, tzinfo=timezone.utc)
    outcomes: list[SyncOutcome] = []
    for season in seasons:
        current = season == seasons[-1]
        source = source_factory(current)
        name = source.name
        last = repository.last_successful_sync(name, competition, season)
        interval = timedelta(days=1 if current else 30)
        if last is not None and now - last < interval:
            outcomes.append(SyncOutcome(competition, season, "fresh"))
            continue

        try:
            batch = source.fetch(RESULTS, FetchContext(competition, season, context_time))
            if batch.source != name:
                raise ValueError("Source identity mismatch")
            matches = list(batch.matches)
            if not matches:
                raise ValueError("Source returned no completed matches; do not mark season fresh")
            imported = repository.import_matches(matches)
            outcome = SyncOutcome(competition, season, "ok", len(matches),
                                  imported, len(batch.warnings))
            repository.record_source_sync(
                source=name, competition=competition, season=season,
                status="ok", fetched=outcome.fetched, inserted=outcome.inserted,
                invalid=outcome.invalid,
            )
        except Exception as exc:
            repository.record_source_sync(
                source=name, competition=competition, season=season,
                status="error", fetched=0, inserted=0, invalid=0,
                error=f"{type(exc).__name__}: {exc}",
            )
            outcome = SyncOutcome(competition, season, "error")
        outcomes.append(outcome)
    return outcomes
