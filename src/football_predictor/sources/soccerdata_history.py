"""Read completed football matches from Soccerdata's MatchHistory provider."""

from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path
import re
from typing import Any, Callable

from football_predictor.domain import FetchContext, MatchResult, ResultBatch
from football_predictor.sources.base import RESULTS


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).split(" ", 1)[0]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        # Football-Data's original CSV uses day-first dates, unlike the
        # normalized pandas timestamps returned by Soccerdata.
        for pattern in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(raw, pattern).date()
            except ValueError:
                continue
        raise


def _recover_legacy_bom_rows(reader: Any, context: FetchContext) -> list[dict]:
    """Handle newly BOM-prefixed pre-2024 Football-Data CSVs.

    Soccerdata parses seasons before 2024-25 as Latin-1. Some upstream
    archived CSVs now begin with a UTF-8 BOM; the resulting `ï»¿Div` header
    causes Soccerdata to raise KeyError('league'). Reuse Soccerdata's own
    download/cache layer and parse only the needed result columns. Never
    silently recover a different schema error or a non-BOM response.
    """
    match = re.fullmatch(r"(20\d{2})-(\d{2})", context.season)
    if not match or int(match[1]) >= 2024:
        raise ValueError("BOM recovery is only for archived pre-2024 seasons")
    start_year = int(match[1])
    if int(match[2]) != (start_year + 1) % 100:
        raise ValueError("Invalid season format")

    selected = reader._selected_leagues
    if len(selected) != 1 or context.competition not in selected:
        raise ValueError("BOM recovery requires one known Soccerdata league")
    league = selected[context.competition]
    if not re.fullmatch(r"[A-Za-z0-9]+", league):
        raise ValueError("Invalid upstream league identifier")

    season = f"{start_year % 100:02d}{match[2]}"
    url = f"https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"
    cache_path = Path(reader.data_dir) / f"{league}_{season}.csv"
    with reader.get(url, cache_path, no_cache=False) as response:
        raw = response.read()
    if not raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("Soccerdata league column absent; no UTF-8 BOM to recover")

    contents = raw[3:]
    try:
        decoded = contents.decode("utf-8")
    except UnicodeDecodeError:
        decoded = contents.decode("latin-1")
    csv_reader = csv.DictReader(StringIO(decoded))
    required = {"Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    if not required.issubset(csv_reader.fieldnames or []):
        raise ValueError("Football-Data CSV is missing required result columns")
    return [
        {"date": row["Date"], "home_team": row["HomeTeam"],
         "away_team": row["AwayTeam"], "FTHG": row["FTHG"],
         "FTAG": row["FTAG"]}
        for row in csv_reader if row.get("Div") == league
    ]


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
        try:
            frame = reader.read_games()
            rows = frame.reset_index().to_dict("records") if hasattr(frame, "reset_index") else frame
        except KeyError as exc:
            if exc.args != ("league",):
                raise
            rows = _recover_legacy_bom_rows(reader, context)
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
