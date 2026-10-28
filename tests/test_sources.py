import unittest
from datetime import date, datetime, timezone

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


if __name__ == "__main__":
    unittest.main()
