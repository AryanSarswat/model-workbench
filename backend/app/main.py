"""FastAPI app entrypoint. Routers are registered here as each feature area lands."""

from fastapi import FastAPI

app = FastAPI(title="model-workbench")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
