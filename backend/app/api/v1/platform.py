from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.adapters import (
    get_deployment_adapter,
    get_gitops_adapter,
    get_metrics_adapter,
    get_security_scanner_adapter,
)
from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/platform", tags=["Platform Health"])

@router.get("/health", response_model=ApiResponse[dict])
async def platform_health(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    adapters = [
        get_deployment_adapter(),
        get_gitops_adapter(),
        get_metrics_adapter(),
        get_security_scanner_adapter(),
    ]
    return ApiResponse(success=True, data={
        "status": "ok",
        "integrations": {
            adapter.adapter_name: {
                "configured": True,
                "is_simulated": adapter.is_simulated,
            }
            for adapter in adapters
        },
    })
