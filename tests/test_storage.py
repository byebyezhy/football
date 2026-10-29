import unittest
from datetime import date

from football_predictor.domain import MatchResult
from football_predictor.storage import PostgresRepository


class FakeCursor:
    def __init__(self, seen):
        self.seen = seen
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, values):
        self.seen.append((query, values))
        self.rowcount = 1


class FakeConnection:
    def __init__(self, seen):
        self.seen = seen

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, values=None):
        self.seen.append((query, values))
        return self

    def cursor(self):
        return FakeCursor(self.seen)


class StorageTests(unittest.TestCase):
    def test_import_uses_bound_parameters_and_keeps_provenance(self):
        seen = []
        repo = PostgresRepository(connect=lambda: FakeConnection(seen))
        repo.ensure_schema()
        fixture = MatchResult("EPL", "2024-25", date(2024, 8, 1),
                              "Arsenal", "Chelsea", 2, 1, "soccerdata", "fixture-id")
        inserted = repo.import_matches([fixture])
        self.assertEqual(inserted, 1)
        sql, parameters = seen[-1]
        self.assertIn("ON CONFLICT DO NOTHING", sql)
        self.assertIn("%s", sql)
        self.assertEqual(parameters[-2:], ("soccerdata", "fixture-id"))
        self.assertNotIn("fixture-id", sql)


if __name__ == "__main__":
    unittest.main()
