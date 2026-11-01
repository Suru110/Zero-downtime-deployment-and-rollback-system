import os
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_ENV: str = "development"
    APP_NAME: str = "ReleasePilot"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Security & Auth
    JWT_SECRET_KEY: str = "insecure-dev-secret-key-change-in-production-12345"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Database: Default to SQLite for seamless local zero-dependency runs if Postgres not set up
    DATABASE_URL: str = "sqlite:///./releasepilot.db"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Adapters & Simulation
    ENABLE_MOCK_ADAPTERS: bool = True
    KUBERNETES_IN_CLUSTER: bool = False
    KUBECONFIG_PATH: Optional[str] = None
    K8S_DEFAULT_NAMESPACE: str = "default"

    # Argo CD
    ARGO_CD_SERVER: str = "http://localhost:8080"
    ARGO_CD_AUTH_TOKEN: str = "mock-token"
    ARGO_CD_INSECURE_SKIP_TLS_VERIFY: bool = True

    # Trivy
    TRIVY_SERVER_URL: str = "http://localhost:4954"
    TRIVY_SEVERITY_THRESHOLD: str = "CRITICAL"

    # Monitoring
    PROMETHEUS_URL: str = "http://localhost:9090"
    GRAFANA_URL: str = "http://localhost:3000"

    # Health Checks & Automated Rollback
    DEFAULT_HEALTH_CHECK_INTERVAL_SECONDS: int = 2
    DEFAULT_HEALTH_CHECK_MAX_ATTEMPTS: int = 4
    DEFAULT_ROLLBACK_ENABLED: bool = True
    REQUIRE_STRONG_JWT_SECRET: bool = False

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        # Ignore unrelated process-level DEBUG values such as debugger names.
        return False

    # Seed Admin Credentials
    ADMIN_INITIAL_USERNAME: str = "admin"
    ADMIN_INITIAL_EMAIL: str = "admin@releasepilot.local"
    ADMIN_INITIAL_PASSWORD: str = "ReleasePilotAdmin2026!"

settings = Settings()
