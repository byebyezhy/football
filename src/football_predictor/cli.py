"""Small local entry points; no background services or implicit network calls."""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

from football_predictor.domain import MatchResult
from football_predictor.models.penaltyblog_adapter import PenaltyblogModel
from football_predictor.sources.base import RESULTS
from football_predictor.sources.soccerdata_history import SoccerdataMatchHistory
from football_predictor.domain import FetchContext


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
                    source="csv", source_id=row.get("source_id") or str(row_number),
                ))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid CSV row {row_number}: {exc}") from exc
    return matches


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="football", description="Football V1 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    preview = sub.add_parser("source-preview", help="Fetch historic results using Soccerdata")
    preview.add_argument("--league", required=True, help="e.g. ENG-Premier League")
    preview.add_argument("--season", required=True, help="e.g. 2024-25")
    preview.add_argument("--as-of", type=date.fromisoformat, default=date.today())

    predict = sub.add_parser("predict-csv", help="Fit historical CSV data and forecast a fixture")
    predict.add_argument("--csv", type=Path, required=True)
    predict.add_argument("--home", required=True)
    predict.add_argument("--away", required=True)
    predict.add_argument("--as-of", type=date.fromisoformat, required=True,
                         help="Train only on matches before YYYY-MM-DD")
    predict.add_argument("--model", choices=["dixon_coles", "poisson"], default="dixon_coles")
    predict.add_argument("--max-goals", type=int, default=15)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "source-preview":
        from datetime import datetime, time, timezone

        context = FetchContext(args.league, args.season,
                               datetime.combine(args.as_of, time.min, tzinfo=timezone.utc))
        batch = SoccerdataMatchHistory().fetch(RESULTS, context)
        print(f"Source: {batch.source}; completed matches: {len(batch.matches)}; "
              f"skipped/invalid rows: {len(batch.warnings)}")
        for match in batch.matches[:5]:
            print(f"{match.played_on}: {match.home_team} {match.home_goals}-"
                  f"{match.away_goals} {match.away_team}")
        return 0

    matches = read_results_csv(args.csv)
    model = PenaltyblogModel(args.model)
    count = model.fit(matches, train_cutoff=args.as_of)
    prediction = model.predict(args.home, args.away, max_goals=args.max_goals)
    print(f"Trained on {count} matches before {args.as_of.isoformat()}")
    print(f"Home {prediction.home_win:.2%} / Draw {prediction.draw:.2%} / "
          f"Away {prediction.away_win:.2%}")
    for home, away, probability in prediction.top_scores(5):
        print(f"{home}-{away}: {probability:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
