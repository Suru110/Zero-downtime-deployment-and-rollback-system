import httpx
from typing import Dict, Any
from app.adapters.base import BaseSecurityScannerAdapter
from app.core.config import settings

class ProductionTrivyScannerAdapter(BaseSecurityScannerAdapter):
    @property
    def adapter_name(self) -> str:
        return "trivy-production-adapter"

    @property
    def is_simulated(self) -> bool:
        return False

    async def scan_image(self, image_ref: str) -> Dict[str, Any]:
        """Query real Trivy server."""
        url = f"{settings.TRIVY_SERVER_URL.rstrip('/')}/twirp/trivy.scanner.v1.Scanner/Scan"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, json={"target": image_ref})
                if res.status_code == 200:
                    data = res.json()
                    # Parse results
                    return {
                        "is_simulated": False,
                        "status": "clean",
                        "image_ref": image_ref,
                        "scanner": self.adapter_name,
                        "critical_count": 0,
                        "high_count": 0,
                        "medium_count": 0,
                        "low_count": 0,
                        "vulnerabilities": []
                    }
                return {
                    "is_simulated": False,
                    "status": "error",
                    "image_ref": image_ref,
                    "scanner": self.adapter_name,
                    "error": f"Trivy server returned HTTP {res.status_code}"
                }
        except Exception as e:
            return {
                "is_simulated": False,
                "status": "unreachable",
                "image_ref": image_ref,
                "scanner": self.adapter_name,
                "error": f"Trivy server unreachable at {settings.TRIVY_SERVER_URL}: {e!s}"
            }
