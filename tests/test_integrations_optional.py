"""Runs with optional dependencies; never contacts a third-party website."""

import importlib.util
import unittest
from datetime import date, timedelta

from football_predictor.backtest import walk_forward
from football_predictor.domain import MatchResult
from football_predictor.models.penaltyblog_adapter import PenaltyblogModel


@unittest.skipUnless(importlib.util.find_spec("penaltyblog"), "penaltyblog not installed")
class PenaltyblogIntegrationTests(unittest.TestCase):
    def test_real_poisson_and_dixon_coles_output(self):
        names = ["A", "B", "C", "D", "E", "F"]
        matches = []
        idx = 0
        for repeat in range(3):
            for home in range(6):
                for away in range(6):
                    if home == away:
                        continue
                    matches.append(MatchResult(
                        "Sample", "2023", date(2023, 1, 1) + timedelta(days=idx),
                        names[home], names[away], (home + repeat) % 4,
                        (away + repeat) % 3, "synthetic", str(idx),
                    ))
                    idx += 1

        for kind in ("poisson", "dixon_coles"):
            with self.subTest(kind=kind):
                model = PenaltyblogModel(kind)
                self.assertEqual(model.fit(matches, train_cutoff=date(2024, 1, 1)), 90)
                prediction = model.predict("A", "B", max_goals=12)
                self.assertAlmostEqual(sum(sum(row) for row in prediction.score_grid), 1.0)
                self.assertEqual(len(prediction.top_scores(3)), 3)

        backtest = walk_forward(matches, lambda: PenaltyblogModel("poisson"),
                                min_training_matches=87, max_goals=12)
        self.assertEqual(backtest.summary()["n_matches"], 3)
        self.assertGreaterEqual(backtest.summary()["rps"], 0)


@unittest.skipUnless(importlib.util.find_spec("soccerdata"), "soccerdata not installed")
class SoccerdataImportTests(unittest.TestCase):
    def test_actual_reader_api_exists(self):
        # Instantiating the reader would access its cache/network: API import only.
        from soccerdata import MatchHistory

        self.assertTrue(callable(MatchHistory.read_games))


if __name__ == "__main__":
    unittest.main()
