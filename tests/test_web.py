import unittest
import os
from datetime import date, timedelta

try:
    import httpx
    from football_predictor.web.app import create_app
except ImportError:
    httpx = None

from football_predictor.domain import MatchResult, ScorePrediction
from football_predictor.forecast_service import ForecastService, ForecastError


class FakeRepository:
    def __init__(self, count=65):
        self.matches = [
            MatchResult("EPL", "2024-25", date(2024, 8, 1) + timedelta(days=i),
                        "Arsenal", "Chelsea", i % 4, i % 3, "fixture", f"match-{i}")
            for i in range(count)
        ]
        self.initialized = False

    def ensure_schema(self):
        self.initialized = True

    def status(self):
        return {"matches": len(self.matches), "latest_match_date": self.matches[-1].played_on.isoformat() if self.matches else None}

    def competitions(self):
        return ["EPL"] if self.matches else []

    def teams(self, competition):
        return ["Arsenal", "Chelsea"] if competition == "EPL" and self.matches else []

    def source_sync_status(self, competition):
        return []

    def recent_backtests(self, competition):
        return []

    def revision(self, competition, as_of):
        rows = self.results(competition, as_of)
        return len(rows), str(len(rows))

    def results(self, competition, as_of, **kwargs):
        return [m for m in self.matches if m.competition == competition and m.played_on < as_of]


class FakePredictionModel:
    fits = 0

    def __init__(self, kind):
        self.kind = kind

    def fit(self, matches, *, train_cutoff):
        self.__class__.fits += 1
        if any(match.played_on >= train_cutoff for match in matches):
            raise AssertionError("Same-day/future results leaked to the model")
        return len(matches)

    def predict(self, home, away, *, max_goals):
        if (home, away) != ("Arsenal", "Chelsea"):
            raise ValueError("Unknown team")
        return ScorePrediction(((0.1, 0.2), (0.3, 0.4)), 0.3, 0.5, 0.2)


class ForecastServiceTests(unittest.TestCase):
    def setUp(self):
        FakePredictionModel.fits = 0

    def test_as_of_day_leakage_and_fit_cache(self):
        repo = FakeRepository()
        service = ForecastService(repo, model_factory=FakePredictionModel)
        as_of = date(2024, 10, 1)
        result = service.forecast("EPL", "Arsenal", "Chelsea", as_of)
        self.assertEqual(result["training_matches"], len(repo.results("EPL", as_of)))
        self.assertEqual(result["top_scores"][0]["score"], "1-1")
        self.assertEqual(FakePredictionModel.fits, 1)
        service.forecast("EPL", "Arsenal", "Chelsea", as_of)
        self.assertEqual(FakePredictionModel.fits, 1)
        service.forecast("EPL", "Arsenal", "Chelsea", date(2024, 10, 2))
        self.assertEqual(FakePredictionModel.fits, 2)

    def test_insufficient_history_rejected(self):
        service = ForecastService(FakeRepository(count=5), model_factory=FakePredictionModel)
        with self.assertRaises(ForecastError):
            service.forecast("EPL", "Arsenal", "Chelsea", date(2025, 1, 1))


@unittest.skipIf(httpx is None, "Install football-predictor[web,test] for API contract tests")
class WebContractTests(unittest.TestCase):
    def test_openapi_and_direct_handlers(self):
        repo = FakeRepository()
        app = create_app(repo, model_factory=FakePredictionModel)
        paths = app.openapi()["paths"]
        self.assertTrue({"/", "/healthz", "/api/status", "/api/predict", "/api/teams",
                         "/api/sources", "/api/backtests"}.issubset(
            {route.path for route in app.routes}))
        self.assertIn("/api/predict", paths)
        endpoints = {route.path: route.endpoint for route in app.routes}
        self.assertEqual(endpoints["/healthz"]()["status"], "ok")
        self.assertEqual(endpoints["/api/status"]()["matches"], 65)
        self.assertEqual(endpoints["/api/competitions"]()["competitions"], ["EPL"])
        self.assertEqual(endpoints["/api/competitions"]()["competition_names_zh"], {"EPL": "EPL"})
        self.assertEqual(endpoints["/api/teams"](competition="EPL")["team_names_zh"],
                         {"Arsenal": "Arsenal", "Chelsea": "Chelsea"})
        self.assertEqual(endpoints["/api/sources"](competition="EPL")["sources"], [])
        self.assertEqual(endpoints["/api/backtests"](competition="EPL")["reports"], [])
        prediction = endpoints["/api/predict"](
            competition="EPL", home="Arsenal", away="Chelsea",
            as_of=date(2025, 1, 1), model="poisson",
        )
        self.assertEqual(prediction["model"], "poisson")
        self.assertEqual(len(prediction["top_scores"]), 4)


@unittest.skipIf(httpx is None or os.environ.get("FOOTBALL_SKIP_HTTP") == "1",
                 "HTTP tests require web dependencies and a functional asyncio threadpool")
class WebHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.repo = FakeRepository()
        # ASGITransport exercises real request routing without a socket or a
        # cross-thread portal; the repository's startup initializer is explicit.
        self.repo.ensure_schema()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(self.repo, model_factory=FakePredictionModel)),
            base_url="http://testserver",
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_home_status_and_discovery(self):
        self.assertTrue(self.repo.initialized)
        page = await self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("fb.linmeng.ai", page.text)
        self.assertIn("历史赛果", page.text)
        self.assertEqual((await self.client.get("/healthz")).json()["status"], "ok")
        self.assertEqual((await self.client.get("/api/status")).json()["matches"], 65)
        self.assertEqual((await self.client.get("/api/competitions")).json()["competitions"], ["EPL"])
        team_data = (await self.client.get("/api/teams?competition=EPL")).json()
        self.assertEqual(team_data["teams"], ["Arsenal", "Chelsea"])
        self.assertEqual(team_data["team_names_zh"], {"Arsenal": "Arsenal", "Chelsea": "Chelsea"})
        self.assertEqual((await self.client.get("/api/backtests?competition=EPL")).json()["reports"], [])
        self.assertEqual((await self.client.get("/api/sources?competition=EPL")).json()["sources"], [])

    async def test_predict_and_bad_input(self):
        params = {"competition": "EPL", "home": "Arsenal", "away": "Chelsea", "as_of": "2025-01-01"}
        reply = await self.client.get("/api/predict", params=params)
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertAlmostEqual(reply.json()["home_win"], 0.3)
        self.assertEqual(reply.json()["model"], "dixon_coles")
        self.assertEqual((await self.client.get("/api/predict", params={**params, "away": "Arsenal"})).status_code, 422)
        self.assertEqual((await self.client.get("/api/predict", params={**params, "as_of": "2024-08-03"})).status_code, 422)
        self.assertEqual((await self.client.get("/api/predict", params={**params, "model": "unknown"})).status_code, 422)

    async def test_empty_data_is_honest(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(FakeRepository(count=0), model_factory=FakePredictionModel)),
            base_url="http://testserver",
        ) as client:
            self.assertEqual((await client.get("/api/competitions")).json()["competitions"], [])
            result = await client.get("/api/predict", params={
                "competition": "EPL", "home": "Arsenal", "away": "Chelsea", "as_of": "2025-01-01",
            })
            self.assertEqual(result.status_code, 422)


if __name__ == "__main__":
    unittest.main()
