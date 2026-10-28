"""Read completed football matches from Soccerdata's MatchHistory provider."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Callable

from football_predictor.domain import FetchContext, MatchResult, ResultBatch
from football_predictor.sources.base import RESULTS


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).split(" ", 1)[0])


def _goals(value: Any) -> int:
    if value is None or str(value).lower() in {"", "nan", "none", "<na>"}:
        raise ValueError("missing goals")
    n = float(value)
    if not n.is_integer() or n < 0:
        raise ValueError("invalid goal count")
    return int(n)


class SoccerdataMatchHistory:
    name = "soccerdata_match_history"
    capabilities = frozenset({RESULTS})

    def __init__(self, *, reader_factory: Callable[..., Any] | None = None,
                 no_cache: bool = False) -> None:
        self._reader_factory = reader_factory
        self._no_cache = no_cache

    def fetch(self, capability: str, context: FetchContext) -> ResultBatch:
        if capability != RESULTS:
            raise ValueError(f"Unsupported capability: {capability}")
        reader_factory = self._reader_factory
        if reader_factory is None:
            try:
                from soccerdata import MatchHistory
            except ImportError as exc:
                raise RuntimeError("Install football-predictor[data] to use Soccerdata") from exc
            reader_factory = MatchHistory

        reader = reader_factory(leagues=[context.competition],
                                seasons=[context.season], no_cache=self._no_cache)
        frame = reader.read_games()
        rows = frame.reset_index().to_dict("records") if hasattr(frame, "reset_index") else frame
        now = datetime.now(timezone.utc)
        matches: list[MatchResult] = []
        warnings: list[str] = []
        for idx, row in enumerate(rows):
            try:
                played_on = _as_date(row["date"])
                # The date alone cannot prove the final whistle time; exclude
                # the entire as-of date conservatively for pre-match snapshots.
                if played_on >= context.as_of_utc.date():
                    continue
                home = str(row.get("home_team") or "").strip()
                away = str(row.get("away_team") or "").strip()
                hg = _goals(row["FTHG"])
                ag = _goals(row["FTAG"])
                source_id = str(row.get("game") or row.get("match_id") or
                                f"{played_on.isoformat()}:{home}:{away}")
                match = MatchResult(context.competition, context.season, played_on,
                                    home, away, hg, ag, self.name, source_id)
                matches.append(match)
            except (KeyError, ValueError, TypeError, OverflowError) as exc:
                warnings.append(f"row {idx}: {exc}")

        return ResultBatch(self.name, now, tuple(matches), tuple(warnings))
