import tempfile
import unittest
from datetime import date
from pathlib import Path

from football_predictor.domain import MatchResult
from football_predictor.results_io import read_results_csv, write_results_csv


class ResultsIOTests(unittest.TestCase):
    def test_round_trip_preserves_source_identity_and_refuses_overwrite(self):
        m = MatchResult("EPL", "2024-25", date(2024, 8, 1),
                        "Arsenal", "Chelsea", 2, 0, "soccerdata_match_history", "id123")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.csv"
            write_results_csv(path, [m])
            self.assertEqual(read_results_csv(path), [m])
            with self.assertRaises(FileExistsError):
                write_results_csv(path, [m])


if __name__ == "__main__":
    unittest.main()
