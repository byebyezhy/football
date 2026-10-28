import unittest
from datetime import date
from types import SimpleNamespace

from football_predictor.domain import MatchResult
from football_predictor.models.penaltyblog_adapter import PenaltyblogModel


class FakeGoalModel:
    def __init__(self, home_goals, away_goals, home_teams, away_teams, **kwargs):
        self.training_count = len(home_goals)

    def fit(self):
        self.fitted = True

    def predict(self, home_team, away_team, **kwargs):
        return SimpleNamespace(grid=[[0.1, 0.2], [0.3, 0.4]],
                               home_win=0.3, draw=0.5, away_win=0.2)


def example(day):
    return MatchResult("EPL", "2024-25", date(2024, 8, day),
                       "A", "B", 2, 1, "sample", f"match-{day}")


class ModelTests(unittest.TestCase):
    def test_training_cutoff_and_grid(self):
        lib = SimpleNamespace(models=SimpleNamespace(
            PoissonGoalsModel=FakeGoalModel, DixonColesGoalModel=FakeGoalModel))
        model = PenaltyblogModel("dixon_coles", library=lib)
        count = model.fit([example(1), example(2), example(5)],
                          train_cutoff=date(2024, 8, 3))
        self.assertEqual(count, 2)
        self.assertAlmostEqual(model.predict("A", "B").draw, 0.5)

    def test_refuses_too_few_matches_or_predict_before_fit(self):
        lib = SimpleNamespace(models=SimpleNamespace(PoissonGoalsModel=FakeGoalModel))
        model = PenaltyblogModel("poisson", library=lib)
        with self.assertRaises(RuntimeError):
            model.predict("A", "B")
        with self.assertRaises(ValueError):
            model.fit([example(1), example(2)], train_cutoff=date(2024, 8, 2))


if __name__ == "__main__":
    unittest.main()
