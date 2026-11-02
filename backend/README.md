# ReleasePilot backend

## Local setup

Create a virtual environment, install `requirements.txt`, copy the repository
`.env.example` to `.env`, and run:

```bash
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

The default configuration uses the simulated adapters. Set
`KUBERNETES_MODE=real` to use the configured Kubernetes context. Keep
`ENABLE_MOCK_ADAPTERS=true` unless Trivy, Argo CD, and Prometheus endpoints are
also configured; Kubernetes mode is independently selectable. Simulated
responses are marked with
`is_simulated=true` and are never presented as live cluster results.

For the local `Registration-login` application, register the image with port
`3000` and health path `/healthz`. Its SQLite database is stored inside the
container at `/app/data/users.db`; use one replica unless a persistent-volume
and single-writer policy are configured.

Users are created through `POST /api/v1/auth/register` or the frontend
registration page. The backend does not create administrator, developer, or
demo accounts during startup. The optional seed command only creates sample
deployment data and never creates user accounts.
