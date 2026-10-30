"""Isolated background sync/backtest process. Never runs inside public API."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import logging
import os
import time

from football_predictor.backtest_service import evaluate_competition
from football_predictor.storage import PostgresRepository
from football_predictor.sync_pipeline import sync_competition


LOGGER = logging.getLogger("football.worker")
# The current production scheduler uses UTC+8; avoid a tzdata dependency in slim images.
LOCAL_ZONE = timezone(timedelta(hours=8))
DEFAULT_LEAGUES = (
    "ENG-Premier League,ESP-La Liga,GER-Bundesliga,ITA-Serie A,FRA-Ligue 1"
)


def run_cycle(repository, *, now: datetime, competitions: tuple[str, ...],
              backtest_days: int = 48) -> None:
    """Refresh real results and periodically create auditable model summaries."""
    as_of = now.astimezone(LOCAL_ZONE).date()
    repository.ensure_schema()
    for competition in competitions:
        try:
            outcomes = sync_competition(repository, competition, as_of=as_of, now=now)
        except Exception:
            LOGGER.exception("Sync failed for %s; continuing with other leagues", competition)
            continue
        for outcome in outcomes:
            LOGGER.info("source=%s season=%s state=%s fetched=%d imported=%d invalid=%d",
                        competition, outcome.season, outcome.status,
                        outcome.fetched, outcome.inserted, outcome.invalid)

        last = repository.last_backtest_at(competition)
        existing = {item["model"] for item in repository.recent_backtests(competition)}
        # Recalculate when newly imported fixtures change the training set;
        # otherwise keep the weekly cadence to limit model fitting costs.
        imported_new_matches = any(item.inserted > 0 for item in outcomes)
        if not imported_new_matches and last is not None and now - last < timedelta(days=7) and \
                {"poisson", "dixon_coles"}.issubset(existing):
            continue
        try:
            reports = evaluate_competition(repository, competition,
                                           as_of=as_of, max_evaluation_dates=backtest_days)
            for report in reports:
                LOGGER.info("backtest competition=%s model=%s samples=%d",
                            competition, report["model"], report["summary"]["n_matches"])
        except Exception:
            LOGGER.exception("Backtesting failed for %s; harvesting remains available", competition)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Run one scheduled cycle for diagnostics")
    args = parser.parse_args()

    hours = float(os.environ.get("FOOTBALL_SYNC_INTERVAL_HOURS", "24"))
    if not 1 <= hours <= 168:
        parser.error("FOOTBALL_SYNC_INTERVAL_HOURS must be 1..168")
    dates = int(os.environ.get("FOOTBALL_BACKTEST_DATES", "48"))
    if not 1 <= dates <= 365:
        parser.error("FOOTBALL_BACKTEST_DATES must be 1..365")
    competitions = tuple(item.strip() for item in
                         os.environ.get("FOOTBALL_SYNC_LEAGUES", DEFAULT_LEAGUES).split(",")
                         if item.strip())
    if not competitions:
        parser.error("At least one competition is required")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    repository = PostgresRepository()
    while True:
        try:
            run_cycle(repository, now=datetime.now(timezone.utc),
                      competitions=competitions, backtest_days=dates)
        except Exception:
            LOGGER.exception("Sync cycle failed; will retry after interval")
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(hours * 3600)


if __name__ == "__main__":
    raise SystemExit(main())
