"""Persisted, off-request empirical model evaluation from real stored scores."""

from __future__ import annotations

from datetime import date
from typing import Callable

from football_predictor.backtest import walk_forward
from football_predictor.models.penaltyblog_adapter import PenaltyblogModel


def evaluate_competition(
    repository,
    competition: str,
    *,
    as_of: date,
    max_evaluation_dates: int = 48,
    min_training_matches: int = 100,
    model_factory: Callable[[str], object] = PenaltyblogModel,
) -> list[dict]:
    """Evaluate recent dates using exclusively older scores for each fixture.

    Both models use the same historical data and evaluation dates. The public
    HTTP endpoint reads saved summaries; it never trains models on demand.
    """
    if not 1 <= max_evaluation_dates <= 365:
        raise ValueError("max_evaluation_dates must be between 1 and 365")
    matches = repository.results(competition, as_of, limit=3000)
    dates = sorted({match.played_on for match in matches})
    if len(matches) <= min_training_matches or not dates:
        return []

    evaluate_from = dates[-max_evaluation_dates]
    reports = []
    for model in ("poisson", "dixon_coles"):
        report = walk_forward(
            matches, lambda kind=model: model_factory(kind),
            min_training_matches=min_training_matches,
            max_goals=15, evaluate_from=evaluate_from,
        )
        if not report.evaluated:
            continue
        summary = report.summary()
        repository.save_backtest_report(
            competition, model, evaluate_from,
            report.evaluated[-1].fixture.played_on, summary,
        )
        reports.append({"model": model, "evaluate_from": evaluate_from,
                        "summary": summary})
    return reports
