import random
from typing import Dict, Any
from app.adapters.base import BaseMetricsAdapter

class MockPrometheusAdapter(BaseMetricsAdapter):
    @property
    def adapter_name(self) -> str:
        return "mock-prometheus-adapter"

    @property
    def is_simulated(self) -> bool:
        return True

    async def query_error_rate(self, app_name: str, namespace: str) -> float:
        """Simulate low HTTP 5xx error rate (0.01% - 0.05%)."""
        return round(random.uniform(0.01, 0.05), 3)

    async def get_telemetry(self, app_name: str, namespace: str) -> Dict[str, Any]:
        return {
            "app_name": app_name,
            "namespace": namespace,
            "is_simulated": True,
            "cpu_usage_cores": round(random.uniform(0.12, 0.45), 2),
            "memory_usage_mb": round(random.uniform(180, 320), 1),
            "requests_per_sec": random.randint(45, 120),
            "p95_latency_ms": round(random.uniform(12, 38), 1),
            "error_rate_pct": round(random.uniform(0.01, 0.04), 3)
        }
