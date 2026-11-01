from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from app.core.config import settings
from app.core.database import init_db, SessionLocal
from app.core.migrations import run_migrations
from app.api.v1.router import api_router
from app.core.logging import get_logger
from app.core.metrics import REQUESTS, REQUEST_LATENCY
from uuid import uuid4
import time

logger = get_logger("releasepilot.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Applying ReleasePilot database migrations...")
    run_migrations()
    logger.info("Ensuring database tables exist...")
    init_db()
    logger.info("ReleasePilot API initialized and ready.")
    yield

app = FastAPI(
    title=settings.APP_NAME,
    description="Reusable Zero-Downtime Deployment & Automated Rollback Platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS configuration for modern frontend dev and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        route = request.scope.get("route")
        route_name = getattr(route, "path", request.url.path)
        REQUESTS.labels(request.method, route_name, "500").inc()
        REQUEST_LATENCY.labels(request.method, route_name).observe(time.perf_counter() - started)
        logger.exception("Unhandled request", extra={"request_id": request_id})
        raise
    route = request.scope.get("route")
    route_name = getattr(route, "path", request.url.path)
    REQUESTS.labels(request.method, route_name, str(response.status_code)).inc()
    REQUEST_LATENCY.labels(request.method, route_name).observe(time.perf_counter() - started)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "Request completed",
        extra={"request_id": request_id, "extra": {
            "method": request.method,
            "route": route_name,
            "status": response.status_code,
        }},
    )
    return response

# Consistent global exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled server error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": str(exc) if settings.DEBUG else "An unexpected internal server error occurred."
            }
        }
    )

# System Health and Observability Endpoints
def _database_ready() -> bool:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Database readiness check failed")
        return False

@app.get("/health/live", tags=["System Health"])
@app.get("/healthz", tags=["System Health"])
def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}

@app.get("/health/ready", tags=["System Health"])
@app.get("/readyz", tags=["System Health"])
def readiness_check():
    ready = _database_ready()
    payload = {"status": "ready" if ready else "not_ready", "database": "connected" if ready else "unavailable"}
    return JSONResponse(status_code=200 if ready else 503, content=payload)

@app.get("/livez", tags=["System Health"])
def liveness_check():
    return {"status": "alive"}

@app.get("/metrics", tags=["System Health"])
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Mount API v1 router
app.include_router(api_router, prefix="/api")
