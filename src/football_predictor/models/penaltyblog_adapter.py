"""Probability-grid adapter for the upstream penaltyblog models."""

from __future__ import annotations

from datetime import date
from typing import Any

from football_predictor.domain import MatchResult, ScorePrediction


class PenaltyblogModel:
    def __init__(self, kind: str = "dixon_coles", *, decay_xi: float = 0,
                 library: Any | None = None) -> None:
        if kind not in {"poisson", "dixon_coles"}:
            raise ValueError("Model must be poisson or dixon_coles")
        if decay_xi < 0:
            raise ValueError("decay_xi must be nonnegative")
        self.kind = kind
        self.decay_xi = decay_xi
        self._library = library
        self._fitted: Any | None = None

    def fit(self, matches: list[MatchResult], *, train_cutoff: date) -> int:
        training = [m for m in matches if m.played_on < train_cutoff]
        if len(training) < 2:
            raise ValueError("At least two completed matches are needed for training")
        if len({m.competition for m in training}) != 1:
            raise ValueError("Train one competition at a time")
        library = self._library
        if library is None:
            try:
                import penaltyblog as library
            except ImportError as exc:
                raise RuntimeError("Install football-predictor[model] to run the model") from exc
        models = library.models
        model_name = "PoissonGoalsModel" if self.kind == "poisson" else "DixonColesGoalModel"
        # Both names appear in published versions of penaltyblog's documentation.
        model_class = getattr(models, model_name, None)
        if model_class is None and self.kind == "dixon_coles":
            model_class = getattr(models, "DixonColesGoalsModel", None)
        if model_class is None:
            raise RuntimeError(f"Installed penaltyblog does not provide {model_name}")
        kwargs: dict[str, Any] = {}
        if self.decay_xi:
            try:
                import pandas as pd
            except ImportError as exc:
                raise RuntimeError("Pandas is required for time-decay weighting") from exc
            dates = pd.Series(pd.to_datetime([m.played_on for m in training]))
            kwargs["weights"] = models.dixon_coles_weights(dates, xi=self.decay_xi)
        model = model_class(
            [m.home_goals for m in training], [m.away_goals for m in training],
            [m.home_team for m in training], [m.away_team for m in training],
            **kwargs,
        )
        model.fit()
        self._fitted = model
        return len(training)

    def predict(self, home_team: str, away_team: str, *, max_goals: int = 15) -> ScorePrediction:
        if self._fitted is None:
            raise RuntimeError("Fit the model before predicting")
        if max_goals < 1:
            raise ValueError("max_goals must be positive")
        result = self._fitted.predict(home_team, away_team,
                                      max_goals=max_goals, normalize=True)
        grid = tuple(tuple(float(value) for value in row) for row in result.grid)
        return ScorePrediction(grid, float(result.home_win), float(result.draw),
                               float(result.away_win))
