import unittest
from datetime import date, datetime, timedelta, timezone

from football_predictor.domain import FetchContext, MatchResult, ScorePrediction


class DomainTests(unittest.TestCase):
    def test_invalid_goals_and_same_team(self):
        base = dict(competition="EPL", season="2024-25", played_on=date(2024, 8, 1),
                    home_team="A", away_team="B", home_goals=1, away_goals=0,
                    source="sample", source_id="one")
        with self.assertRaises(ValueError):
            MatchResult(**{**base, "home_goals": -1})
        with self.assertRaises(ValueError):
            MatchResult(**{**base, "home_team": "B"})
        with self.assertRaises(ValueError):
            MatchResult(**{**base, "away_goals": 0.5})

    def test_aware_as_of_is_required(self):
        with self.assertRaises(ValueError):
            FetchContext("EPL", "2024-25", datetime(2024, 1, 1))
        with self.assertRaises(ValueError):
            FetchContext("EPL", "2024-25", datetime(2024, 1, 1,
                                                   tzinfo=timezone(timedelta(hours=8))))
        FetchContext("EPL", "2024-25", datetime(2024, 1, 1, tzinfo=timezone.utc))

    def test_score_grid_normalizes_and_top_scores(self):
        pred = ScorePrediction(((0.1, 0.2), (0.3, 0.4)), 0.3, 0.5, 0.2)
        self.assertEqual(pred.top_scores(2), [(1, 1, 0.4), (1, 0, 0.3)])
        with self.assertRaises(ValueError):
            ScorePrediction(((0.1, 0.2), (0.3, 0.3)), 0.3, 0.5, 0.2)
        with self.assertRaises(ValueError):
            ScorePrediction(((0.1, 0.2), (0.3, 0.4)), 0.2, 0.5, 0.3)


if __name__ == "__main__":
    unittest.main()
