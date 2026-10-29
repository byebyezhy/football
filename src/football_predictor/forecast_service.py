"""Bounded, cached forecasts based only on matches before the as-of date."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date
from threading import Lock
from typing import Callable

from football_predictor.models.penaltyblog_adapter import PenaltyblogModel


class ForecastError(ValueError):
    """Invalid, incomplete or insufficient input data for a forecast."""


class ForecastService:
    def __init__(self, repository, *, model_factory: Callable = PenaltyblogModel,
                 minimum_matches: int = 30, cache_size: int = 8):
        self.repository = repository
        self.model_factory = model_factory
        self.minimum_matches = minimum_matches
        self.cache_size = cache_size
        self._cache: OrderedDict[tuple, tuple[object, int]] = OrderedDict()
        self._lock = Lock()

    def forecast(self, competition: str, home: str, away: str, as_of: date,
                 kind: str = "dixon_coles") -> dict:
        if not competition.strip() or not home.strip() or not away.strip() or home == away:
            raise ForecastError("请选择不同的主客队与有效联赛")
        if kind not in {"poisson", "dixon_coles"}:
            raise ForecastError("不支持的预测模型")
        count, revision = self.repository.revision(competition, as_of)
        if count < self.minimum_matches:
            raise ForecastError(f"该联赛赛前历史数据不足（{count} 场），至少需要 {self.minimum_matches} 场")

        key = (competition, as_of, kind, count, revision)
        with self._lock:
            cached = self._cache.get(key)
            if cached is None:
                matches = self.repository.results(competition, as_of)
                if len(matches) < self.minimum_matches:
                    raise ForecastError("可用于训练的历史比赛不足")
                model = self.model_factory(kind)
                training_count = model.fit(matches, train_cutoff=as_of)
                cached = (model, training_count)
                self._cache[key] = cached
                if len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)
            else:
                self._cache.move_to_end(key)
            model, training_count = cached
            # Predict while holding the lock: upstream models may not be thread-safe.
            try:
                prediction = model.predict(home, away, max_goals=10)
            except (ValueError, KeyError) as exc:
                raise ForecastError("球队不在该联赛历史训练数据中") from exc

        return {
            "competition": competition,
            "home_team": home,
            "away_team": away,
            "as_of": as_of.isoformat(),
            "model": kind,
            "training_matches": training_count,
            "home_win": prediction.home_win,
            "draw": prediction.draw,
            "away_win": prediction.away_win,
            "top_scores": [
                {"score": f"{h}-{a}", "probability": prob}
                for h, a, prob in prediction.top_scores(5)
            ],
            "score_grid": prediction.score_grid,
            "warning": "试验性统计预测，尚未完成真实数据基线验证；不构成投注建议。",
        }
