import unittest
from datetime import date, timedelta

from football_predictor.backtest_service import evaluate_competition
from football_predictor.domain import MatchResult, ScorePrediction


SAMPLE = ScorePrediction(((0.1, 0.2), (0.3, 0.4)), 0.3, 0.5, 0.2)


class FakeModel:
    def __init__(self, kind, log):
        self.kind = kind
        self.log = log

    def fit(self, matches, *, train_cutoff):
        self.log.append((self.kind, train_cutoff, tuple(m.played_on for m in matches)))
        return len(matches)

    def predict(self, home, away, *, max_goals):
        return SAMPLE


class FakeRepository:
    def __init__(self):
        self.matches = [
            MatchResult("ENG-Premier League", "2024-25",
                        date(2024, 8, 1) + timedelta(days=i),
                        "Arsenal", "Chelsea", 1, 0, "test", f"fixture-{i}")
            for i in range(10)
        ]
        self.saved = []

    def results(self, competition, as_of, *, limit):
        return [m for m in self.matches if m.competition == competition and m.played_on < as_of]

    def save_backtest_report(self, *args):
        self.saved.append(args)


class BacktestServiceTests(unittest.TestCase):
    def test_same_recent_dates_both_models_no_leakage_and_persisted(self):
        repo = FakeRepository()
        log = []
        reports = evaluate_competition(
            repo, "ENG-Premier League", as_of=date(2024, 8, 12),
            max_evaluation_dates=3, min_training_matches=3,
            model_factory=lambda kind: FakeModel(kind, log),
        )
        self.assertEqual([r["model"] for r in reports], ["poisson", "dixon_coles"])
        self.assertTrue(all(r["summary"]["n_matches"] == 3 for r in reports))
        self.assertEqual(len(repo.saved), 2)
        self.assertEqual(repo.saved[0][2], date(2024, 8, 8))
        for kind, cutoff, training_dates in log:
            self.assertTrue(training_dates)
            self.assertTrue(all(day < cutoff for day in training_dates), kind)

    def test_no_history_leaves_no_fabricated_report(self):
        repo = FakeRepository()
        repo.matches = []
        self.assertEqual(evaluate_competition(repo, "ENG-Premier League",
                                              as_of=date(2024, 8, 12)), [])
        self.assertEqual(repo.saved, [])


if __name__ == "__main__":
    unittest.main()
