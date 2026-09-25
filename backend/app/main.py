"""FastAPI app entrypoint. Routers are registered here as each feature area lands."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api_config.router import router as config_router
from app.chat.router import router as chat_router
from app.db import init_db
from app.discovery.router import router as discovery_router
from app.downloads.router import router as downloads_router
from app.errors import WorkbenchError
from app.tools.router import router as tools_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title="model-workbench", lifespan=lifespan)
# NOTE: order matters -- discovery_router's /{model_id:path} is a catch-all that would
# swallow downloads_router's /models/downloaded routes if registered first (same hazard as
# within discovery/router.py itself; see its route-ordering comment).
app.include_router(downloads_router)
app.include_router(discovery_router)
app.include_router(chat_router)
app.include_router(config_router)
app.include_router(tools_router)


@app.exception_handler(WorkbenchError)
async def workbench_error_handler(request: Request, exc: WorkbenchError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
