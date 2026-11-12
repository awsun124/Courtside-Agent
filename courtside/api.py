from contextlib import asynccontextmanager, suppress
import asyncio
import os
import sqlite3
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .service import NewsService, PROJECT_ROOT, RefreshError
from .schedule import run_schedule
from .llm import ChatProvider
from .investigation import InvestigationSettings
from .storage import finish_sample_agent, read_briefings, start_sample_agent

DataMode = Literal["live", "sample"]


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: DataMode = "live"
    days: int = Field(default=3, ge=1, le=7)
    max_requests: int = Field(default=3, ge=1, le=5)


class SampleInvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


def create_app(database=None, env_file=None, settings_file=None, collector=None, clock=None, investigation_file=None, sources_file=None, scheduled=None):
    public_read_only = os.environ.get("COURTSIDE_PUBLIC_READ_ONLY", "false").lower() == "true"
    database_path = database or os.environ.get("COURTSIDE_DATABASE") or PROJECT_ROOT / "artifacts/courtside.db"
    origins = [origin.strip() for origin in os.environ.get("COURTSIDE_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()]
    automatic = scheduled if scheduled is not None else collector is None and clock is None

    @asynccontextmanager
    async def lifespan(app):
        app.state.news = NewsService(database_path,
                                     env_file, settings_file, collector, clock, investigation_file, sources_file)
        app.state.news.daily_schedule = automatic
        task = asyncio.create_task(run_schedule(app.state.news)) if automatic else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="Court Side", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def protect_public_writes(request: Request, call_next):
        if public_read_only and request.method not in {"GET", "HEAD", "OPTIONS"}:
            return JSONResponse(status_code=403, content={"detail": "This demo serves saved results only. Collection runs on the server's daily schedule."})
        return await call_next(request)

    @app.exception_handler(sqlite3.Error)
    async def database_error(request: Request, error):
        return JSONResponse(status_code=503, content={"detail": "The database is unavailable. Try again later."})

    @app.get("/health")
    def health(request: Request):
        read_briefings(request.app.state.news.database, "live", limit=1)
        return {"status": "ok"}

    @app.get("/api/stats")
    def stats(request: Request):
        from .stats import read_stats, season_for
        service = request.app.state.news
        return read_stats(service.database, season_for(service.clock()), service.clock())

    @app.get("/api/briefings/latest")
    def latest(request: Request, mode: DataMode = "live"):
        result = request.app.state.news.latest(mode)
        result["status"]["public_read_only"] = public_read_only
        return result

    @app.get("/api/briefings")
    def history(request: Request, mode: DataMode = "live", limit: int = Query(default=10, ge=1, le=50)):
        briefings = read_briefings(request.app.state.news.database, mode, limit)
        return {"data_mode": mode, "briefings": [dict(briefing_id=briefing["briefing_id"], as_of=briefing["as_of"],
                experimental=briefing["experimental"], story_count=len(briefing["stories"]),
                candidate_count=len(briefing["candidates"])) for briefing in briefings]}

    @app.get("/api/briefings/{briefing_id}")
    def saved_briefing(briefing_id: int, request: Request, mode: DataMode = "live"):
        saved = read_briefings(request.app.state.news.database, mode, limit=1, briefing_id=briefing_id)
        if not saved:
            raise HTTPException(404, "Saved briefing not found")
        return saved[0]

    @app.get("/api/stories/{story_id}")
    def story(story_id: str, request: Request, mode: DataMode = "live", briefing_id: int | None = Query(default=None, ge=1)):
        saved = request.app.state.news.story(story_id, mode, briefing_id)
        if saved is None:
            raise HTTPException(404, "Story not found in this briefing")
        return saved

    @app.post("/api/refresh")
    def refresh(body: RefreshRequest, request: Request):
        if automatic and body.mode == "live":
            raise HTTPException(403, "News updates automatically at 6 AM Eastern. Reload to read the saved briefing.")
        try:
            return request.app.state.news.refresh(body.mode, body.days, body.max_requests)
        except RefreshError as error:
            headers = {"Retry-After": str(error.retry_after)} if error.retry_after else None
            raise HTTPException(error.status_code, str(error), headers=headers) from None

    @app.post("/api/sample/investigate")
    def sample_investigate(body: SampleInvestigationRequest, request: Request):
        from scripts.check_agent import run_check

        service = request.app.state.news
        now = service.clock()
        job = start_sample_agent(service.database, now)
        if "error" in job:
            headers = {"Retry-After": str(job["retry_after"])} if job.get("retry_after") else None
            raise HTTPException(job["status_code"], job["error"], headers=headers)
        provider = None
        try:
            limits = InvestigationSettings(max_stories=1, max_steps=8, max_steps_per_story=8,
                max_seconds=20, max_llm_calls=5, max_articles_per_story=3,
                max_input_characters=16000, max_output_tokens=500)
            provider = ChatProvider(limits, service.env_file, sample_only=True)
            report = run_check(live=True, env_file=service.env_file, sample_only=True, provider=provider)
            record = report["investigation"]
            result = dict(data_mode="sample", model=report.get("model"), passed=report["passed"],
                          checks=report["checks"], optional_checks=report["optional_checks"],
                          note=report["note"], target=report["target"])
            requests_used = provider.calls_made
            finish_sample_agent(service.database, job["id"], service.clock(), record.get("status", "incomplete"),
                                requests_used, result)
            return result
        except ValueError:
            finish_sample_agent(service.database, job["id"], service.clock(), "unavailable", provider.calls_made if provider else 0,
                                error="Sample AI is unavailable or returned an unusable result")
            raise HTTPException(503, "Sample AI is unavailable. Check the server-side opt-in and provider settings.") from None
        except Exception:
            finish_sample_agent(service.database, job["id"], service.clock(), "failed", provider.calls_made if provider else 0,
                                error="Sample investigation could not finish")
            raise HTTPException(502, "Sample investigation could not finish. Try again later.") from None

    return app


app = create_app()
