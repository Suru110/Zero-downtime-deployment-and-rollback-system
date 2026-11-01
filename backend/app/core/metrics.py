from prometheus_client import Counter, Histogram

REQUESTS = Counter(
    "releasepilot_http_requests_total",
    "HTTP requests handled by ReleasePilot.",
    ("method", "route", "status"),
)
REQUEST_LATENCY = Histogram(
    "releasepilot_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
)
DEPLOYMENT_DURATION = Histogram(
    "releasepilot_deployment_duration_seconds",
    "Deployment execution duration in seconds.",
    ("strategy", "status"),
)
ROLLOUT_FAILURES = Counter(
    "releasepilot_rollout_failures_total",
    "Rollout operations that failed before verification completed.",
    ("adapter", "simulated"),
)
ROLLBACKS = Counter(
    "releasepilot_rollbacks_total",
    "Rollback operations by outcome.",
    ("automated", "status", "simulated"),
)
HEALTH_CHECKS = Counter(
    "releasepilot_health_checks_total",
    "Recorded deployment health checks.",
    ("check_type", "status", "simulated"),
)
