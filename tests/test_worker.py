import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from football_predictor.worker import run_cycle


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


if __name__ == "__main__":
    unittest.main()
