"""Small local entry points; no background services or implicit network calls."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time, timezone
from pathlib import Path

from football_predictor.backtest import walk_forward
from football_predictor.models.penaltyblog_adapter import PenaltyblogModel
from football_predictor.results_io import read_results_csv, write_results_csv
from football_predictor.sources.base import RESULTS
from football_predictor.sources.soccerdata_history import SoccerdataMatchHistory
from football_predictor.domain import FetchContext


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="football", description="Football V1 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    preview = sub.add_parser("source-preview", help="Fetch historic results using Soccerdata")
    preview.add_argument("--league", required=True, help="e.g. ENG-Premier League")
    preview.add_argument("--season", required=True, help="e.g. 2024-25")
    preview.add_argument("--as-of", type=date.fromisoformat, default=date.today())

    fetch = sub.add_parser("fetch-results", help="Export completed games from Soccerdata to CSV")
    fetch.add_argument("--league", required=True)
    fetch.add_argument("--season", required=True)
    fetch.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    fetch.add_argument("--output", type=Path, required=True)

    import_csv = sub.add_parser("import-results", help="Import normalized CSV results into PostgreSQL")
    import_csv.add_argument("--csv", type=Path, required=True)

    predict = sub.add_parser("predict-csv", help="Fit historical CSV data and forecast a fixture")
    predict.add_argument("--csv", type=Path, required=True)
    predict.add_argument("--home", required=True)
    predict.add_argument("--away", required=True)
    predict.add_argument("--as-of", type=date.fromisoformat, required=True,
                         help="Train only on matches before YYYY-MM-DD")
    predict.add_argument("--model", choices=["dixon_coles", "poisson"], default="dixon_coles")
    predict.add_argument("--max-goals", type=int, default=15)

    backtest = sub.add_parser("backtest-csv", help="Date-grouped walk-forward evaluation")
    backtest.add_argument("--csv", type=Path, required=True)
    backtest.add_argument("--output", type=Path, required=True)
    backtest.add_argument("--model", choices=["dixon_coles", "poisson"], default="dixon_coles")
    backtest.add_argument("--min-training", type=int, default=100)
    backtest.add_argument("--max-goals", type=int, default=15)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in {"source-preview", "fetch-results"}:
        context = FetchContext(args.league, args.season,
                               datetime.combine(args.as_of, time.min, tzinfo=timezone.utc))
        batch = SoccerdataMatchHistory().fetch(RESULTS, context)
        if args.command == "fetch-results":
            write_results_csv(args.output, batch.matches)
            print(f"Saved {len(batch.matches)} matches to {args.output}; "
                  f"invalid rows: {len(batch.warnings)}")
            return 0
        print(f"Source: {batch.source}; completed matches: {len(batch.matches)}; "
              f"skipped/invalid rows: {len(batch.warnings)}")
        for match in batch.matches[:5]:
            print(f"{match.played_on}: {match.home_team} {match.home_goals}-"
                  f"{match.away_goals} {match.away_team}")
        return 0

    matches = read_results_csv(args.csv)
    if args.command == "import-results":
        from football_predictor.storage import PostgresRepository
        repository = PostgresRepository()
        repository.ensure_schema()
        imported = repository.import_matches(matches)
        print(f"Imported {imported} new fixtures; skipped {len(matches) - imported} duplicates")
        return 0
    if args.command == "backtest-csv":
        report = walk_forward(
            matches, lambda: PenaltyblogModel(args.model),
            min_training_matches=args.min_training, max_goals=args.max_goals,
        )
        payload = {
            "summary": report.summary(),
            "skipped": report.skipped,
            "evaluated": [
                {
                    "date": e.fixture.played_on.isoformat(),
                    "source_id": e.fixture.source_id,
                    "home_team": e.fixture.home_team,
                    "away_team": e.fixture.away_team,
                    "actual_score": [e.fixture.home_goals, e.fixture.away_goals],
                    "training_matches": e.training_matches,
                    "home_draw_away": [e.prediction.home_win, e.prediction.draw, e.prediction.away_win],
                    "top_scores": e.prediction.top_scores(5),
                    "brier": e.brier,
                    "rps": e.ranked_probability_score,
                    "log_loss": e.log_loss,
                    "exact_score_log_loss": e.exact_score_log_loss,
                }
                for e in report.evaluated
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        print(json.dumps(payload["summary"], indent=2))
        return 0

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
