"""Local API for saved NBA briefings and bounded manual refreshes."""
from contextlib import asynccontextmanager
import sqlite3
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .service import NewsService, PROJECT_ROOT, RefreshError
from .storage import read_briefings

DataMode = Literal["live", "sample"]


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: DataMode = "live"
    days: int = Field(default=3, ge=1, le=7)
    max_requests: int = Field(default=3, ge=1, le=5)


def create_app(database=None, env_file=None, settings_file=None, collector=None, clock=None, investigation_file=None, sources_file=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.news = NewsService(database or PROJECT_ROOT / "artifacts/courtside.db",
                                     env_file, settings_file, collector, clock, investigation_file, sources_file)
        yield

    app = FastAPI(title="Court Side", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.exception_handler(sqlite3.Error)
    async def database_error(request: Request, error):
        return JSONResponse(status_code=503, content={"detail": "The database is unavailable. Try again later."})

    @app.get("/health")
    def health(request: Request):
        read_briefings(request.app.state.news.database, "live", limit=1)
        return {"status": "ok"}

    @app.get("/api/briefings/latest")
    def latest(request: Request, mode: DataMode = "live"):
        return request.app.state.news.latest(mode)

    @app.get("/api/briefings")
    def history(request: Request, mode: DataMode = "live", limit: int = Query(default=10, ge=1, le=50)):
        briefings = read_briefings(request.app.state.news.database, mode, limit)
        return {"data_mode": mode, "briefings": [dict(briefing_id=briefing["briefing_id"], as_of=briefing["as_of"],
                experimental=briefing["experimental"], story_count=len(briefing["stories"]),
                candidate_count=len(briefing["candidates"])) for briefing in briefings]}

    @app.get("/api/stories/{story_id}")
    def story(story_id: str, request: Request, mode: DataMode = "live", briefing_id: int | None = Query(default=None, ge=1)):
        saved = request.app.state.news.story(story_id, mode, briefing_id)
        if saved is None:
            raise HTTPException(404, "Story not found in this briefing")
        return saved

    @app.post("/api/refresh")
    def refresh(body: RefreshRequest, request: Request):
        try:
            return request.app.state.news.refresh(body.mode, body.days, body.max_requests)
        except RefreshError as error:
            headers = {"Retry-After": str(error.retry_after)} if error.retry_after else None
            raise HTTPException(error.status_code, str(error), headers=headers) from None

    return app


app = create_app()
