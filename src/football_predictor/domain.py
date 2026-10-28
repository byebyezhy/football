"""Shared contracts that do not depend on a particular data or model vendor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from math import isfinite


@dataclass(frozen=True)
class MatchResult:
    competition: str
    season: str
    played_on: date
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    source: str
    source_id: str

    def __post_init__(self) -> None:
        if not self.competition or not self.season or not self.source or not self.source_id:
            raise ValueError("Competition, season, source and source_id are required")
        if not self.home_team or not self.away_team or self.home_team == self.away_team:
            raise ValueError("Two distinct teams are required")
        if type(self.home_goals) is not int or type(self.away_goals) is not int:
            raise ValueError("Goals must be integers")
        if min(self.home_goals, self.away_goals) < 0:
            raise ValueError("Goals cannot be negative")


@dataclass(frozen=True)
class FetchContext:
    competition: str
    season: str
    as_of_utc: datetime

    def __post_init__(self) -> None:
        if not self.competition or not self.season:
            raise ValueError("Competition and season are required")
        if self.as_of_utc.tzinfo is None or self.as_of_utc.utcoffset() != timedelta(0):
            raise ValueError("as_of_utc must be explicitly in UTC")

    @classmethod
    def current(cls, competition: str, season: str) -> FetchContext:
        return cls(competition, season, datetime.now(timezone.utc))


@dataclass(frozen=True)
class ResultBatch:
    source: str
    fetched_at_utc: datetime
    matches: tuple[MatchResult, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScorePrediction:
    score_grid: tuple[tuple[float, ...], ...]  # home goals = row, away goals = column
    home_win: float
    draw: float
    away_win: float

    def __post_init__(self) -> None:
        n = len(self.score_grid)
        if n == 0 or any(len(row) != n for row in self.score_grid):
            raise ValueError("Score grid must be a nonempty square matrix")
        vals = [p for row in self.score_grid for p in row]
        if not all(isfinite(p) and p >= 0 for p in vals):
            raise ValueError("Score probabilities must be finite and nonnegative")
        if abs(sum(vals) - 1.0) > 1e-5:
            raise ValueError("Score probabilities must sum to one")
        probs = (self.home_win, self.draw, self.away_win)
        if not all(isfinite(p) and 0 <= p <= 1 for p in probs):
            raise ValueError("1X2 probabilities must be between zero and one")
        if abs(sum(probs) - 1.0) > 1e-5:
            raise ValueError("1X2 probabilities must sum to one")
        derived = (
            sum(self.score_grid[h][a] for h in range(n) for a in range(h)),
            sum(self.score_grid[i][i] for i in range(n)),
            sum(self.score_grid[h][a] for h in range(n) for a in range(h + 1, n)),
        )
        if any(abs(x - y) > 1e-5 for x, y in zip(probs, derived)):
            raise ValueError("1X2 probabilities must match the score grid")

    def top_scores(self, count: int = 3) -> list[tuple[int, int, float]]:
        if count < 1:
            raise ValueError("Count must be positive")
        scores = [(home, away, prob) for home, row in enumerate(self.score_grid)
                  for away, prob in enumerate(row)]
        return sorted(scores, key=lambda item: (-item[2], item[0], item[1]))[:count]
