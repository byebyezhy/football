import unittest
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path

from football_predictor.domain import FetchContext
from football_predictor.sources.base import RESULTS, XG, SourceRegistry
from football_predictor.sources.soccerdata_history import SoccerdataMatchHistory


class FakeReader:
    def __init__(self, **kwargs):
        self.config = kwargs

    def read_games(self):
        return [
            {"date": date(2024, 8, 1), "home_team": "A", "away_team": "B",
             "FTHG": 2, "FTAG": 1, "game": "g1"},
            {"date": date(2024, 8, 2), "home_team": "C", "away_team": "D",
             "FTHG": None, "FTAG": None, "game": "g2"},
            {"date": date(2024, 9, 1), "home_team": "A", "away_team": "C",
             "FTHG": 0, "FTAG": 0, "game": "future"},
        ]


class BomArchiveReader:
    _selected_leagues = {"ENG-Premier League": "E0"}
    data_dir = Path("/tmp/football-test-bom")
    csv_data = (
        b"\xef\xbb\xbfDiv,Date,HomeTeam,AwayTeam,FTHG,FTAG\n"
        b"E0,13/08/2021,Brentford,Arsenal,2,0\n"
        b"E0,14/08/2021,Man United,Leeds,5,1\n"
        b"E0,15/08/2021,Leicester,Wolves,,\n"
    )

    def __init__(self, **kwargs):
        self.config = kwargs
        self.requested = None

    def read_games(self):
        raise KeyError("league")

    def get(self, url, filepath, no_cache=False):
        self.requested = (url, filepath, no_cache)
        return BytesIO(self.csv_data)


class SourceTests(unittest.TestCase):
    def test_safely_filters_incomplete_or_future_games(self):
        adapter = SoccerdataMatchHistory(reader_factory=FakeReader)
        context = FetchContext("ENG-Premier League", "2024-25",
                               datetime(2024, 8, 5, tzinfo=timezone.utc))
        batch = adapter.fetch(RESULTS, context)
        self.assertEqual(len(batch.matches), 1)
        self.assertEqual(batch.matches[0].source_id, "g1")
        self.assertEqual(len(batch.warnings), 1)

    def test_registry_capabilities(self):
        registry = SourceRegistry()
        registry.register(SoccerdataMatchHistory(reader_factory=FakeReader))
        self.assertEqual(registry.sources_for(RESULTS), ("soccerdata_match_history",))
        self.assertEqual(registry.sources_for(XG), ())
        with self.assertRaises(ValueError):
            registry.fetch("soccerdata_match_history", XG,
                           FetchContext.current("EPL", "2024-25"))
        with self.assertRaises(ValueError):
            registry.register(SoccerdataMatchHistory(reader_factory=FakeReader))

    def test_old_bom_csv_recovers_without_suppressing_invalid_rows(self):
        reader = BomArchiveReader()
        adapter = SoccerdataMatchHistory(reader_factory=lambda **kwargs: reader)
        context = FetchContext("ENG-Premier League", "2021-22",
                               datetime(2026, 10, 29, tzinfo=timezone.utc))
        result = adapter.fetch(RESULTS, context)
        self.assertEqual(len(result.matches), 2)
        self.assertEqual(result.matches[0].played_on, date(2021, 8, 13))
        self.assertEqual(result.matches[0].home_team, "Brentford")
        self.assertEqual(result.matches[0].source, "soccerdata_match_history")
        self.assertEqual(len(result.warnings), 1)
        self.assertEqual(
            reader.requested,
            ("https://www.football-data.co.uk/mmz4281/2122/E0.csv",
             Path("/tmp/football-test-bom/E0_2122.csv"), False),
        )

    def test_recovery_rejects_non_bom_or_unrelated_keyerror(self):
        context = FetchContext("ENG-Premier League", "2021-22",
                               datetime(2026, 10, 29, tzinfo=timezone.utc))
        reader = BomArchiveReader()
        reader.csv_data = reader.csv_data.removeprefix(b"\xef\xbb\xbf")
        adapter = SoccerdataMatchHistory(reader_factory=lambda **kwargs: reader)
        with self.assertRaisesRegex(ValueError, "no UTF-8 BOM"):
            adapter.fetch(RESULTS, context)

        class MissingDateReader(BomArchiveReader):
            def read_games(self):
                raise KeyError("date")

        reader = MissingDateReader()
        adapter = SoccerdataMatchHistory(reader_factory=lambda **kwargs: reader)
        with self.assertRaisesRegex(KeyError, "date"):
            adapter.fetch(RESULTS, context)
        self.assertIsNone(reader.requested)


if __name__ == "__main__":
    unittest.main()
