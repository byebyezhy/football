import unittest
from datetime import date, datetime, timezone

from football_predictor.domain import MatchResult, ResultBatch
from football_predictor.sync_pipeline import season_keys, sync_competition


NOW = datetime(2026, 10, 29, 8, 0, tzinfo=timezone.utc)


class FakeRepository:
    def __init__(self):
        self.seen = set()
        self.history = []
        self.last = {}

    def last_successful_sync(self, source, competition, season):
        return self.last.get((source, competition, season))

    def import_matches(self, matches):
        fresh = 0
        for match in matches:
            identity = (match.competition, match.season, match.played_on,
                        match.home_team, match.away_team)
            if identity not in self.seen:
                self.seen.add(identity)
                fresh += 1
        return fresh

    def record_source_sync(self, **kwargs):
        self.history.append(kwargs)
        if kwargs["status"] == "ok":
            self.last[(kwargs["source"], kwargs["competition"], kwargs["season"])] = NOW


class FakeSource:
    name = "test_history"

    def __init__(self, no_cache, failures=frozenset()):
        self.no_cache = no_cache
        self.failures = failures

    def fetch(self, capability, context):
        if context.season in self.failures:
            raise RuntimeError("source temporarily unavailable")
        match = MatchResult(context.competition, context.season,
                            date(int(context.season[:4]), 8, 10),
                            "Arsenal", "Chelsea", 1, 0,
                            self.name, context.season)
        return ResultBatch(self.name, NOW, (match,))


class SyncPipelineTests(unittest.TestCase):
    def test_european_season_boundary(self):
        self.assertEqual(season_keys(date(2026, 10, 29)), [
            "2021-22", "2022-23", "2023-24", "2024-25", "2025-26", "2026-27",
        ])
        self.assertEqual(season_keys(date(2026, 2, 1), completed_seasons=1),
                         ["2024-25", "2025-26"])
        with self.assertRaises(ValueError):
            season_keys(date(2026, 10, 29), completed_seasons=0)

    def test_incremental_idempotent_and_current_season_nocache(self):
        repo = FakeRepository()
        cache_flags = []

        def factory(no_cache):
            cache_flags.append(no_cache)
            return FakeSource(no_cache)

        first = sync_competition(repo, "ENG-Premier League", as_of=NOW.date(),
                                 now=NOW, source_factory=factory, completed_seasons=1)
        self.assertEqual([(r.status, r.inserted) for r in first], [("ok", 1), ("ok", 1)])
        self.assertEqual(cache_flags, [False, True])
        second = sync_competition(repo, "ENG-Premier League", as_of=NOW.date(),
                                  now=NOW, source_factory=factory, completed_seasons=1)
        self.assertTrue(all(r.status == "fresh" for r in second))
        self.assertEqual(len(repo.seen), 2)

    def test_one_broken_season_does_not_block_imports(self):
        repo = FakeRepository()
        results = sync_competition(
            repo, "ENG-Premier League", as_of=NOW.date(), now=NOW,
            source_factory=lambda no_cache: FakeSource(no_cache, {"2025-26"}),
            completed_seasons=1,
        )
        self.assertEqual([r.status for r in results], ["error", "ok"])
        self.assertEqual(len(repo.seen), 1)
        self.assertIn("source temporarily unavailable", repo.history[0]["error"])


if __name__ == "__main__":
    unittest.main()
