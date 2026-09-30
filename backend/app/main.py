from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.model_config import load_env, log_effective_config

load_env()

from app.api.routes.chat import router as chat_router  # noqa: E402
from app.api.routes.config import router as config_router  # noqa: E402
from app.api.routes.stream import router as stream_router  # noqa: E402
from app.api.routes.templates import router as templates_router  # noqa: E402
from app.api.routes.knowledge import router as knowledge_router  # noqa: E402
from app.api.routes.parse import router as parse_router  # noqa: E402
from app.api.routes.session import router as session_router  # noqa: E402
from app.api.routes.system import router as system_router  # noqa: E402
from app.api.routes.workflow import router as workflow_router  # noqa: E402
from app.api.routes.e4 import router as e4_router  # noqa: E402
from app.mcp import get_manager  # noqa: E402

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_effective_config()
    manager = get_manager()
    try:
        await manager.start()
    except Exception as exc:
        logger.error("MCP manager failed to start: %s", exc)
    app.state.mcp_manager = manager
    try:
        yield
    finally:
        await manager.stop()


app = FastAPI(title="Inventor + ANSYS MCP Orchestrator", version="2.0.0", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(knowledge_router)
app.include_router(parse_router)
app.include_router(session_router)
app.include_router(system_router)
app.include_router(workflow_router)
app.include_router(e4_router)
app.include_router(config_router)
app.include_router(templates_router)
app.include_router(stream_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


_FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
