"""Leakage-aware, date-grouped walk-forward evaluation for score models."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from math import log
from typing import Callable, Protocol

from football_predictor.domain import MatchResult, ScorePrediction


class ForecastModel(Protocol):
    def fit(self, matches: list[MatchResult], *, train_cutoff: date) -> int: ...
    def predict(self, home_team: str, away_team: str, *, max_goals: int) -> ScorePrediction: ...


@dataclass(frozen=True)
class EvaluatedMatch:
    fixture: MatchResult
    training_matches: int
    prediction: ScorePrediction
    brier: float
    ranked_probability_score: float
    log_loss: float
    exact_score_log_loss: float
    exact_score_in_grid: bool
    top1_hit: bool
    top3_hit: bool
    top5_hit: bool


@dataclass(frozen=True)
class BacktestReport:
    evaluated: tuple[EvaluatedMatch, ...]
    skipped: tuple[str, ...]

    def summary(self) -> dict[str, float | int]:
        if not self.evaluated:
            raise ValueError("No matches were evaluated")
        count = len(self.evaluated)
        avg = lambda field: sum(getattr(row, field) for row in self.evaluated) / count
        return {
            "n_matches": count,
            "skipped_matches": len(self.skipped),
            "brier": avg("brier"),
            "rps": avg("ranked_probability_score"),
            "log_loss": avg("log_loss"),
            "exact_score_log_loss": avg("exact_score_log_loss"),
            "exact_top1_accuracy": avg("top1_hit"),
            "exact_top3_accuracy": avg("top3_hit"),
            "exact_top5_accuracy": avg("top5_hit"),
            "actual_score_outside_grid": sum(not item.exact_score_in_grid for item in self.evaluated),
        }


def _evaluate(match: MatchResult, pred: ScorePrediction, training_matches: int) -> EvaluatedMatch:
    actual = 0 if match.home_goals > match.away_goals else 1 if match.home_goals == match.away_goals else 2
    probabilities = (pred.home_win, pred.draw, pred.away_win)
    target = tuple(float(i == actual) for i in range(3))
    brier = sum((p - y) ** 2 for p, y in zip(probabilities, target))
    rps = ((probabilities[0] - target[0]) ** 2 +
           (probabilities[0] + probabilities[1] - target[0] - target[1]) ** 2) / 2
    in_grid = match.home_goals < len(pred.score_grid) and match.away_goals < len(pred.score_grid)
    exact_prob = pred.score_grid[match.home_goals][match.away_goals] if in_grid else 0.0
    score = (match.home_goals, match.away_goals)
    top5 = [(h, a) for h, a, _ in pred.top_scores(5)]
    return EvaluatedMatch(
        fixture=match, training_matches=training_matches, prediction=pred,
        brier=brier, ranked_probability_score=rps,
        log_loss=-log(max(probabilities[actual], 1e-12)),
        exact_score_log_loss=-log(max(exact_prob, 1e-12)),
        exact_score_in_grid=in_grid,
        top1_hit=score in top5[:1], top3_hit=score in top5[:3], top5_hit=score in top5,
    )


def walk_forward(
    matches: list[MatchResult],
    model_factory: Callable[[], ForecastModel],
    *,
    min_training_matches: int = 100,
    max_goals: int = 15,
) -> BacktestReport:
    """Predict each date using only matches strictly before that date.

    This isolates completed results at date granularity. It does *not* establish
    that external odds, lineup or xG values were available at historical kickoff.
    Those features require independent published-at / as-of snapshots.
    """
    if min_training_matches < 2 or max_goals < 1:
        raise ValueError("Invalid backtest limits")
    if len({m.competition for m in matches}) > 1:
        raise ValueError("Backtest only one competition at a time")
    if len({(m.source, m.source_id) for m in matches}) != len(matches):
        raise ValueError("Duplicate source match IDs")

    grouped: dict[date, list[MatchResult]] = defaultdict(list)
    for item in matches:
        grouped[item.played_on].append(item)

    historical: list[MatchResult] = []
    evaluated: list[EvaluatedMatch] = []
    skipped: list[str] = []
    for day in sorted(grouped):
        fixtures = sorted(grouped[day], key=lambda m: (m.source, m.source_id))
        if len(historical) < min_training_matches:
            skipped.extend(f"{day}: insufficient history: {m.source_id}" for m in fixtures)
            historical.extend(fixtures)
            continue

        known_teams = {team for m in historical for team in (m.home_team, m.away_team)}
        eligible = [m for m in fixtures if m.home_team in known_teams and m.away_team in known_teams]
        skipped.extend(f"{day}: unseen team: {m.source_id}" for m in fixtures if m not in eligible)
        if eligible:
            model = model_factory()
            training_count = model.fit(historical, train_cutoff=day)
            for match in eligible:
                try:
                    pred = model.predict(match.home_team, match.away_team, max_goals=max_goals)
                except (KeyError, ValueError) as exc:
                    skipped.append(f"{day}: failed to predict {match.source_id}: {exc}")
                    continue
                evaluated.append(_evaluate(match, pred, training_count))
        # Only after predicting every fixture on the day may results enter training.
        historical.extend(fixtures)

    return BacktestReport(tuple(evaluated), tuple(skipped))
