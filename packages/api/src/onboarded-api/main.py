"""
App factory.

    create_app(settings) → FastAPI
      lifespan  loads every tenant once into app.state.store (DomainStore)
      errors    ApiError subclasses → RFC 9457 problem+json, one place
      CORS      Settings.cors_origins (portal dev server by default)

Run:  python -m onboarded_api            (uvicorn, reads OB_API_* env)
      uvicorn onboarded_api.main:app     (module-level app from env)
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from onboarded_api import __version__
from onboarded_api.errors import ApiError
from onboarded_api.routers import dba, domain, scan, system
from onboarded_api.services.dba_service import dba_available
from onboarded_api.services.domain_store import DomainStore
from onboarded_api.settings import Settings

PROBLEM = "application/problem+json"


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse({"type": "about:blank", "title": title, "status": status, "detail": detail},
                        status_code=status, media_type=PROBLEM)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.store = DomainStore(settings.tenants_dir, settings.core_scripts).load()
        app.state.dba_available = dba_available()
        yield

    app = FastAPI(title="Onboarded API", version=__version__, lifespan=lifespan,
                  responses={404: {"model": None, "description": "problem+json"}})

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return _problem(exc.status, exc.title, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        msgs = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        return _problem(422, "Invalid request", msgs)

    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["GET", "POST"], allow_headers=["*"])
    app.include_router(system.router)
    app.include_router(domain.router)
    app.include_router(scan.router)
    app.include_router(dba.router)
    return app


def __getattr__(name: str):
    # `uvicorn onboarded_api.main:app` — build lazily so importing this module
    # in tests never reads the environment.
    if name == "app":
        return create_app()
    raise AttributeError(name)
