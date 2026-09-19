"""FastAPI app entrypoint. Routers are registered here as each feature area lands."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.discovery.router import router as discovery_router
from app.errors import WorkbenchError

app = FastAPI(title="model-workbench")
app.include_router(discovery_router)


@app.exception_handler(WorkbenchError)
async def workbench_error_handler(request: Request, exc: WorkbenchError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
