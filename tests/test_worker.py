import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from football_predictor.sync_pipeline import SyncOutcome
from football_predictor.worker import DEFAULT_LEAGUES, run_cycle


NOW = datetime(2026, 10, 29, 10, tzinfo=timezone.utc)


class FakeRepository:
    def __init__(self, fresh=False):
        self.initialized = False
        self.fresh = fresh

    def ensure_schema(self):
        self.initialized = True

    def last_backtest_at(self, competition):
        return NOW - timedelta(days=1) if self.fresh else None

    def recent_backtests(self, competition):
        return [{"model": "poisson"}, {"model": "dixon_coles"}] if self.fresh else []


class WorkerTests(unittest.TestCase):
    def test_default_enabled_leagues_cover_five_countries(self):
        self.assertEqual(set(DEFAULT_LEAGUES.split(",")), {
            "ENG-Premier League", "ESP-La Liga", "GER-Bundesliga",
            "ITA-Serie A", "FRA-Ligue 1",
        })
        compose = (Path(__file__).resolve().parents[1] / "compose.yaml").read_text()
        self.assertIn("${FOOTBALL_SYNC_LEAGUES:-" + DEFAULT_LEAGUES + "}", compose)

    @patch("football_predictor.worker.evaluate_competition", return_value=[])
    @patch("football_predictor.worker.sync_competition", return_value=[])
    def test_default_five_leagues_each_receive_their_own_cycle(self, sync, evaluate):
        run_cycle(FakeRepository(), now=NOW,
                  competitions=tuple(DEFAULT_LEAGUES.split(",")))
        self.assertEqual(sync.call_count, 5)
        self.assertEqual(evaluate.call_count, 5)

    @patch("football_predictor.worker.evaluate_competition", return_value=[])
    @patch("football_predictor.worker.sync_competition", return_value=[])
    def test_first_cycle_syncs_and_backtests(self, fetch, evaluate):
        repo = FakeRepository()
        run_cycle(repo, now=NOW, competitions=("ENG-Premier League",))
        self.assertTrue(repo.initialized)
        fetch.assert_called_once()
        evaluate.assert_called_once()

    @patch("football_predictor.worker.evaluate_competition")
    @patch("football_predictor.worker.sync_competition", return_value=[])
    def test_recent_two_model_reports_do_not_retrain_daily(self, fetch, evaluate):
        repo = FakeRepository(fresh=True)
        run_cycle(repo, now=NOW, competitions=("ENG-Premier League",))
        fetch.assert_called_once()
        evaluate.assert_not_called()

    @patch("football_predictor.worker.evaluate_competition", return_value=[])
    @patch("football_predictor.worker.sync_competition", return_value=[
        SyncOutcome("ESP-La Liga", "2026-27", "ok", fetched=3, inserted=3),
    ])
    def test_new_results_trigger_backtest_even_with_recent_report(self, fetch, evaluate):
        run_cycle(FakeRepository(fresh=True), now=NOW,
                  competitions=("ESP-La Liga",))
        evaluate.assert_called_once()

    @patch("football_predictor.worker.evaluate_competition", return_value=[])
    @patch("football_predictor.worker.sync_competition")
    def test_one_failed_league_does_not_block_other_leagues(self, fetch, evaluate):
        def sync_side_effect(repository, competition, **kwargs):
            if competition == "ENG-Premier League":
                raise RuntimeError("upstream unavailable")
            return []

        fetch.side_effect = sync_side_effect
        with self.assertLogs("football.worker", level="ERROR") as captured:
            run_cycle(FakeRepository(), now=NOW,
                      competitions=("ENG-Premier League", "ESP-La Liga"))
        self.assertIn("upstream unavailable", " ".join(captured.output))
        self.assertEqual(fetch.call_count, 2)
        evaluate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
