from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.projects import router as projects_router
from app.api.v1.environments import router as environments_router
from app.api.v1.releases import router as releases_router
from app.api.v1.deployments import router as deployments_router
from app.api.v1.health_checks import router as health_checks_router
from app.api.v1.rollbacks import router as rollbacks_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.audit import router as audit_router
from app.api.v1.platform import router as platform_router

api_router = APIRouter(prefix="/v1")

api_router.include_router(auth_router)
api_router.include_router(projects_router)
api_router.include_router(projects_router, prefix="/applications")
api_router.include_router(environments_router)
api_router.include_router(releases_router)
api_router.include_router(deployments_router)
api_router.include_router(health_checks_router)
api_router.include_router(rollbacks_router)
api_router.include_router(metrics_router)
api_router.include_router(audit_router)
api_router.include_router(platform_router)
