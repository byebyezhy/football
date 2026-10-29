"""Real PostgreSQL schema regression; enabled only against an ephemeral CI DB."""

import os
import unittest
from datetime import date

from football_predictor.domain import MatchResult
from football_predictor.storage import PostgresRepository


@unittest.skipUnless(os.environ.get("FOOTBALL_TEST_DATABASE") == "1",
                     "Requires the isolated PostgreSQL CI service")
class PostgresIntegrationTests(unittest.TestCase):
    def test_additive_v03_schema_and_queries_preserve_match_data(self):
        repo = PostgresRepository()
        repo.ensure_schema()
        sample = MatchResult("ENG-Premier League", "2024-25", date(2024, 8, 10),
                             "Arsenal", "Chelsea", 2, 1,
                             "ci-fixture", "ci-unique-id")
        self.assertEqual(repo.import_matches([sample]), 1)
        self.assertEqual(repo.import_matches([sample]), 0)
        self.assertEqual(repo.status()["matches"], 1)
        self.assertEqual(len(repo.results("ENG-Premier League", date(2024, 8, 11))), 1)

        repo.record_source_sync(source="ci-fixture", competition="ENG-Premier League",
                                season="2024-25", status="ok", fetched=1,
                                inserted=0, invalid=0)
        self.assertIsNotNone(repo.last_successful_sync(
            "ci-fixture", "ENG-Premier League", "2024-25"))
        entries = repo.source_sync_status("ENG-Premier League")
        self.assertEqual(entries[0]["season"], "2024-25")
        self.assertEqual(entries[0]["status"], "ok")

        report_summary = {"n_matches": 1, "brier": 0.4, "exact_top5_accuracy": 1.0}
        repo.save_backtest_report("ENG-Premier League", "poisson",
                                  date(2024, 8, 10), date(2024, 8, 10), report_summary)
        reports = repo.recent_backtests("ENG-Premier League")
        self.assertEqual(reports[0]["model"], "poisson")
        self.assertEqual(reports[0]["summary"], report_summary)
        self.assertIsNotNone(repo.last_backtest_at("ENG-Premier League"))
        self.assertEqual(repo.status()["matches"], 1)


if __name__ == "__main__":
    unittest.main()
