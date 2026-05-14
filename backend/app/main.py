from __future__ import annotations

from contextlib import asynccontextmanager, suppress
import os
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .publishers import WECHAT_BROWSER_MANAGER
from .routes import (
    build_agent_html_router,
    build_base_router,
    build_browser_router,
    build_content_router,
    build_intel_router,
    build_runtime_router,
    build_settings_router,
    build_wechat_router,
)
from .routes.common import set_store
from .store import StudioStore
from .store_base import load_version_manifest


store = StudioStore()
set_store(store)

VERSION_MANIFEST = load_version_manifest()
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
RUNTIME_DIR = Path(__file__).resolve().parents[2] / "runtime"
BACKEND_PID_FILE = RUNTIME_DIR / "backend.pid"
scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
SCHEDULER_TICK_SECONDS = 10


def _cors_origins() -> list[str]:
    raw = str(os.getenv("CORS_ORIGINS") or "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return ["http://127.0.0.1:8000", "http://localhost:8000"]


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, SystemError, ValueError):
        return False
    return True


def _acquire_backend_pid_lock() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if BACKEND_PID_FILE.exists():
        try:
            existing_pid = int(BACKEND_PID_FILE.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            existing_pid = 0
        if existing_pid and existing_pid != os.getpid() and _pid_is_alive(existing_pid):
            raise RuntimeError(f"后端已在运行 (PID={existing_pid})，请先停止旧进程再启动。")
    BACKEND_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def _release_backend_pid_lock() -> None:
    try:
        if BACKEND_PID_FILE.exists():
            recorded_pid = int(BACKEND_PID_FILE.read_text(encoding="utf-8").strip() or "0")
            if recorded_pid == os.getpid():
                BACKEND_PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _acquire_backend_pid_lock()
    WECHAT_BROWSER_MANAGER.startup()
    if not scheduler.running:
        scheduler.add_job(
            store.run_automation_cycle,
            "interval",
            seconds=SCHEDULER_TICK_SECONDS,
            id="automation-cycle",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )
        scheduler.start()
        store.reset_runtime_on_boot(message="服务启动后自动运行保持关闭，需要在驾驶舱手动启动。")
    try:
        yield
    finally:
        if scheduler.running:
            with suppress(Exception):
                scheduler.shutdown(wait=False)
        store.reset_runtime_on_boot(message="服务关闭时已清空自动运行状态。")
        WECHAT_BROWSER_MANAGER.shutdown()
        _release_backend_pid_lock()


app = FastAPI(
    title="Auto News Studio API",
    version=str(VERSION_MANIFEST.get("version") or "0.2.8"),
    description="自动化新闻助手运营后台 API，覆盖信息采集、候选选题、公众号草稿和浏览器会话。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

app.include_router(build_base_router(FRONTEND_DIST))
app.include_router(build_intel_router())
app.include_router(build_runtime_router())
app.include_router(build_content_router())
app.include_router(build_agent_html_router())
app.include_router(build_browser_router())
app.include_router(build_wechat_router())
app.include_router(build_settings_router())
