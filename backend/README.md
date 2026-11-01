# ReleasePilot backend

## Local setup

Create a virtual environment, install `requirements.txt`, copy the repository
`.env.example` to `.env`, and run:

```bash
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

The default configuration uses the simulated adapters. Set
`ENABLE_MOCK_ADAPTERS=false` only when a Kubernetes context, Argo CD, Trivy,
and Prometheus endpoints are configured. Simulated responses are marked with
`is_simulated=true` and are never presented as live cluster results.

Users are created through `POST /api/v1/auth/register` or the frontend
registration page. The backend does not create administrator, developer, or
demo accounts during startup. The optional seed command only creates sample
deployment data and never creates user accounts.
