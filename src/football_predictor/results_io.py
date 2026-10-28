"""Explicit, standard CSV persistence for historical match results."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from football_predictor.domain import MatchResult


RESULT_FIELDS = ("competition", "season", "date", "home_team", "away_team",
                 "home_goals", "away_goals", "source", "source_id")


def read_results_csv(path: Path) -> list[MatchResult]:
    matches: list[MatchResult] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            try:
                matches.append(MatchResult(
                    competition=row["competition"], season=row["season"],
                    played_on=date.fromisoformat(row["date"]),
                    home_team=row["home_team"], away_team=row["away_team"],
                    home_goals=int(row["home_goals"]),
                    away_goals=int(row["away_goals"]),
                    source=row.get("source") or "csv", source_id=row.get("source_id") or str(row_number),
                ))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid CSV row {row_number}: {exc}") from exc
    return matches


def write_results_csv(path: Path, matches: tuple[MatchResult, ...] | list[MatchResult]) -> None:
    """Create only; never silently overwrite a user's historical data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        for m in matches:
            writer.writerow({
                "competition": m.competition, "season": m.season,
                "date": m.played_on.isoformat(),
                "home_team": m.home_team, "away_team": m.away_team,
                "home_goals": m.home_goals, "away_goals": m.away_goals,
                "source": m.source, "source_id": m.source_id,
            })
