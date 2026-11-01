from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from app.core.config import settings
from app.core.database import init_db, SessionLocal
from app.api.v1.router import api_router
from app.core.logging import get_logger

logger = get_logger("releasepilot.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing ReleasePilot Database tables...")
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
