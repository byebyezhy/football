import unittest
from datetime import date

from football_predictor.backtest import walk_forward
from football_predictor.domain import MatchResult, ScorePrediction


SAMPLE_GRID = ScorePrediction(((0.1, 0.2), (0.3, 0.4)), 0.3, 0.5, 0.2)


def game(day, home, away, score, source_id):
    return MatchResult("EPL", "2024-25", date(2024, 8, day), home, away,
                       score[0], score[1], "fixture", source_id)


class SpyModel:
    def __init__(self, log):
        self.log = log

    def fit(self, matches, *, train_cutoff):
        self.log.append((train_cutoff, [m.played_on for m in matches]))
        return len(matches)

    def predict(self, home_team, away_team, *, max_goals):
        return SAMPLE_GRID


class BacktestTests(unittest.TestCase):
    def setUp(self):
        self.matches = [
            game(1, "A", "B", (1, 0), "1"),
            game(1, "C", "D", (0, 1), "2"),
            game(2, "A", "C", (0, 0), "3"),
            game(2, "B", "D", (1, 0), "4"),
            game(3, "B", "C", (1, 1), "5"),
        ]

    def test_same_date_results_never_leak(self):
        log = []
        report = walk_forward(self.matches, lambda: SpyModel(log), min_training_matches=2)
        self.assertEqual(len(report.evaluated), 3)
        self.assertEqual([e.training_matches for e in report.evaluated], [2, 2, 4])
        for cutoff, training_dates in log:
            self.assertTrue(all(day < cutoff for day in training_dates))
        self.assertAlmostEqual(report.summary()["exact_top1_accuracy"], 1 / 3)
        self.assertEqual(report.summary()["skipped_matches"], 2)

    def test_duplicate_result_identity_rejected(self):
        with self.assertRaises(ValueError):
            walk_forward(self.matches + [self.matches[0]],
                         lambda: SpyModel([]), min_training_matches=2)

    def test_no_evaluated_matches(self):
        report = walk_forward(self.matches, lambda: SpyModel([]), min_training_matches=100)
        with self.assertRaises(ValueError):
            report.summary()


if __name__ == "__main__":
    unittest.main()
