"""
FastAPI application factory.

Serves the FOA data through a REST API consumed by the web frontend.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from .routes import health, opportunities, search, tags, export


def create_app() -> FastAPI:
    app = FastAPI(
        title="ISSR Funding Intelligence API",
        description="AI-Powered Funding Opportunity Discovery for ISSR",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # CORS for frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(
        opportunities.router, prefix="/api/opportunities", tags=["opportunities"]
    )
    app.include_router(search.router, prefix="/api/search", tags=["search"])
    app.include_router(tags.router, prefix="/api/tags", tags=["tags"])
    app.include_router(export.router, prefix="/api/export", tags=["export"])

    # Serve frontend static files
    frontend_dir = Path(__file__).parent.parent.parent.parent / "frontend"
    if frontend_dir.exists() and (frontend_dir / "index.html").exists():
        app.mount(
            "/",
            StaticFiles(directory=str(frontend_dir), html=True),
            name="frontend",
        )

    return app


app = create_app()
