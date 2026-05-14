from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


def build_base_router(frontend_dist: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/")
    def frontend_index():
        if frontend_dist.exists():
            return FileResponse(frontend_dist / "index.html")
        return {"status": "frontend-not-built"}

    return router
