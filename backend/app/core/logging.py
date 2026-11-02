import logging
import json
import re
from datetime import datetime
from typing import Any, Dict
from app.core.config import settings

# Sensitive keys to scrub from logs
SENSITIVE_PATTERNS = [
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"authorization", re.IGNORECASE),
    re.compile(r"kubeconfig", re.IGNORECASE),
    re.compile(r"key", re.IGNORECASE),
]

def sanitize_data(data: Any) -> Any:
    """Recursively scrub sensitive fields from dictionaries and lists."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if any(pattern.search(str(k)) for pattern in SENSITIVE_PATTERNS):
                sanitized[k] = "******[REDACTED]******"
            else:
                sanitized[k] = sanitize_data(v)
        return sanitized
    if isinstance(data, list):
        return [sanitize_data(item) for item in data]
    return data

class StructuredFormatter(logging.Formatter):
    """Formats log records as clean structured JSON with redaction."""
    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            log_obj["context"] = sanitize_data(record.extra)
        for field in ("request_id", "deployment_id"):
            value = getattr(record, field, None)
            if value:
                log_obj[field] = value
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)

def get_logger(name: str = "releasepilot") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = StructuredFormatter()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
        logger.propagate = False
    return logger

logger = get_logger("releasepilot.core")
