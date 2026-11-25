from contextlib import asynccontextmanager
from os import getenv
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.controller import router as core_router
from app.core.service import bootstrap as bootstrap_core
from app.database import connect
from app.workflows.controller import router as workflow_router
from app.workflows.service import bootstrap as bootstrap_workflows


@asynccontextmanager
async def lifespan(_: FastAPI):
    with connect() as connection:
        # Serialize startup so two API processes do not migrate at the same time.
        connection.execute("SELECT pg_advisory_xact_lock(80403001)")
        bootstrap_core(connection)
        bootstrap_workflows(connection)
    yield


app = FastAPI(title="Accounting Office", lifespan=lifespan)

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def allowed_browser_origins(public_url):
    expected = f"{public_url.scheme}://{public_url.netloc}"
    if public_url.scheme != "http" or public_url.hostname not in LOOPBACK_HOSTS:
        return {expected}
    port = f":{public_url.port}" if public_url.port is not None else ""
    return {f"http://localhost{port}", f"http://127.0.0.1{port}", f"http://[::1]{port}"}


@app.middleware("http")
async def verify_browser_origin(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        public_url = urlsplit(getenv("APP_BASE_URL", "http://localhost:8080"))
        if origin is not None and origin not in allowed_browser_origins(public_url):
            return JSONResponse({"detail": "請從事務所網站重新操作。"}, status_code=403)
    return await call_next(request)


app.include_router(core_router, prefix="/api")
app.include_router(workflow_router, prefix="/api")


@app.get("/api/health", include_in_schema=False)
def health():
    with connect() as connection:
        connection.execute("SELECT 1")
    return {"status": "ok"}
