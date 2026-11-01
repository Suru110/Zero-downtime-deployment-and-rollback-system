import asyncio
from typing import Dict, Any
from app.adapters.base import BaseSecurityScannerAdapter

class MockTrivyScannerAdapter(BaseSecurityScannerAdapter):
    @property
    def adapter_name(self) -> str:
        return "mock-trivy-scanner"

    @property
    def is_simulated(self) -> bool:
        return True

    async def scan_image(self, image_ref: str) -> Dict[str, Any]:
        """Simulate realistic vulnerability scan with vulnerability catalog."""
        await asyncio.sleep(0.4)
        
        # If image tag contains 'vulnerable' or 'cve', simulate critical findings
        if "vulnerable" in image_ref.lower() or "cve" in image_ref.lower():
            return {
                "is_simulated": True,
                "status": "critical",
                "image_ref": image_ref,
                "scanner": self.adapter_name,
                "critical_count": 2,
                "high_count": 4,
                "medium_count": 7,
                "low_count": 12,
                "vulnerabilities": [
                    {
                        "cve_id": "CVE-2024-38816",
                        "severity": "CRITICAL",
                        "package": "org.springframework:spring-webmvc",
                        "installed_version": "5.3.18",
                        "fixed_version": "5.3.39",
                        "description": "Path traversal vulnerability leading to potential RCE."
                    },
                    {
                        "cve_id": "CVE-2024-21626",
                        "severity": "CRITICAL",
                        "package": "runc",
                        "installed_version": "1.1.11",
                        "fixed_version": "1.1.12",
                        "description": "Container breakout via file descriptor leak."
                    },
                    {
                        "cve_id": "CVE-2024-24790",
                        "severity": "HIGH",
                        "package": "net/http (golang)",
                        "installed_version": "1.21.5",
                        "fixed_version": "1.21.11",
                        "description": "Unexpected HTTP header smuggling behavior."
                    }
                ]
            }
        
        # Clean image simulation
        return {
            "is_simulated": True,
            "status": "clean",
            "image_ref": image_ref,
            "scanner": self.adapter_name,
            "critical_count": 0,
            "high_count": 0,
            "medium_count": 1,
            "low_count": 3,
            "vulnerabilities": [
                {
                    "cve_id": "CVE-2023-45853",
                    "severity": "LOW",
                    "package": "zlib",
                    "installed_version": "1.2.11",
                    "fixed_version": "1.2.12",
                    "description": "Integer overflow in MiniZip."
                }
            ]
        }
