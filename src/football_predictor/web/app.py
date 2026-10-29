"""FastAPI app for the first self-hosted football prediction website."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from football_predictor.forecast_service import ForecastError, ForecastService
from football_predictor.storage import PostgresRepository


INDEX = Path(__file__).parent / "static" / "index.html"


def create_app(repository=None, *, model_factory=None) -> FastAPI:
    repo = repository if repository is not None else PostgresRepository()
    service_options = {"model_factory": model_factory} if model_factory is not None else {}
    forecast_service = ForecastService(repo, **service_options)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        repo.ensure_schema()
        yield

    app = FastAPI(title="凌盟足球预测", version="0.2.0", lifespan=lifespan,
                  docs_url="/api/docs", redoc_url=None,
                  openapi_url="/api/openapi.json")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(INDEX, media_type="text/html")

    @app.get("/healthz", tags=["operations"])
    def healthz():
        return {"status": "ok", "service": "football-api"}

    @app.get("/api/status", tags=["operations"])
    def status():
        try:
            stats = repo.status()
        except Exception as exc:
            raise HTTPException(status_code=503, detail="数据库暂不可用") from exc
        return {"status": "ready", "site": "fb.linmeng.ai", **stats}

    @app.get("/api/competitions", tags=["data"])
    def competitions():
        try:
            return {"competitions": repo.competitions()}
        except Exception as exc:
            raise HTTPException(status_code=503, detail="数据库暂不可用") from exc

    @app.get("/api/teams", tags=["data"])
    def teams(competition: str = Query(min_length=1, max_length=80)):
        try:
            return {"competition": competition, "teams": repo.teams(competition)}
        except Exception as exc:
            raise HTTPException(status_code=503, detail="数据库暂不可用") from exc

    @app.get("/api/predict", tags=["prediction"])
    def predict(
        competition: str = Query(min_length=1, max_length=80),
        home: str = Query(min_length=1, max_length=80),
        away: str = Query(min_length=1, max_length=80),
        as_of: date = Query(),
        model: str = Query(default="dixon_coles", pattern="^(poisson|dixon_coles)$"),
    ):
        if home == away:
            raise HTTPException(status_code=422, detail="主队和客队不能相同")
        try:
            return forecast_service.forecast(competition, home, away, as_of, model)
        except ForecastError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail="预测模型暂不可用") from exc

    return app


app = create_app()
