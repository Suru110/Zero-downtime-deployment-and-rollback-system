# ReleasePilot

ReleasePilot is a mock-first deployment orchestration platform for registering
applications and immutable releases, deploying through an adapter, verifying
readiness and HTTP smoke tests, recording audit history, and restoring the
last known-good release.

The default local adapter is explicitly simulated. It does not contact
Kubernetes, and simulated results are labelled `is_simulated=true`. A real
cluster path is available separately and fails safely when Kubernetes
credentials or connectivity are unavailable.

## Architecture and request flow

- **Frontend:** React, TypeScript, Vite, Axios, Tailwind CSS.
- **Backend:** FastAPI, Pydantic, SQLAlchemy, Alembic.
- **Database:** PostgreSQL for shared/deployed environments; SQLite fallback
  for local development and tests.
- **Adapters:** mock and production Kubernetes, mock/production Trivy,
  mock/production Prometheus, and optional Argo CD.
- **Operations:** Docker Compose, Kubernetes manifests, Helm, GitHub Actions,
  optional Prometheus/Grafana.

The browser calls `/api/v1` through Axios. Authentication uses
`POST /api/v1/auth/login-json`; protected requests send the returned JWT as a
Bearer token.

Deployment flow:

1. Register a project, environment, and release.
2. Create a deployment request.
3. Scan the image with the configured scanner adapter.
4. Deploy with the mock or Kubernetes adapter.
5. Record readiness, smoke-test, and metrics checks.
6. Mark the deployment active, or mark it failed and run policy-controlled
   rollback.
7. Expose deployment logs, health checks, rollback history, and audit events.

The database stores users, projects, environments, releases, deployments,
health checks, rollback events, and audit logs. Alembic migrations are the
authoritative schema changes; automatic table creation is only a local safety
net.

## Prerequisites

For standalone development:

- Python 3.10 or newer.
- Node.js 18 or newer and npm.
- Docker Desktop and Compose v2 are optional.
- Helm, kubectl, Minikube, or kind are optional for Kubernetes work.

## Local setup without a cloud account

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item ..\.env.example .env
```

Edit `backend/.env` or the repository `.env` used by the process. For a
zero-dependency local run, use:

```dotenv
DATABASE_URL=sqlite:///./releasepilot.db
ENABLE_MOCK_ADAPTERS=true
APP_ENV=development
JWT_SECRET_KEY=replace-with-a-long-random-local-secret
```

Apply migrations:

```powershell
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The backend uses `backend/releasepilot.db` when `DATABASE_URL` is not set.
Startup applies Alembic migrations before serving requests. If an existing
legacy SQLite database has no Alembic revision row, startup detects its
verified baseline, stamps that baseline, and upgrades it without deleting
records.

The API is available at `http://localhost:8000/docs`. Liveness is
`GET /health/live`; readiness is `GET /health/ready` and also checks the
database. Create accounts from the public Register page. No user accounts are created
automatically during startup. The optional `python -m app.core.seed` command
only creates sample deployment data and never creates users.

To reset only a local development database (never use this against production),
stop the backend and remove `backend/releasepilot.db`, then run
`alembic upgrade head` again. For the Docker PostgreSQL volume, use
`docker compose down -v` only when intentionally discarding local data.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

The UI is available at `http://localhost:5173`. Set
`VITE_API_URL=/api/v1` when using the Vite/Nginx proxy, or set it to a full
backend URL for a separately hosted API.

After signing in, register an application, add a release, select an
environment, and trigger a deployment. The mock adapter supports successful
and intentionally failing verification flows so deployment history and
rollback records can be exercised without cloud credentials.

Example API flow after registering an account:

```powershell
$login = Invoke-RestMethod http://localhost:8000/api/v1/auth/login `
  -Method Post -ContentType 'application/json' `
  -Body '{"email":"you@example.com","password":"YourPassword123"}'
$headers = @{ Authorization = "Bearer $($login.data.access_token)" }
Invoke-RestMethod http://localhost:8000/api/v1/projects `
  -Method Post -Headers $headers -ContentType 'application/json' `
  -Body '{"name":"example-service","git_repo":"https://github.com/example/example-service","image_repository":"example/example-service","default_port":8080,"health_path":"/healthz"}'
```

## Environment variables

Copy [.env.example](.env.example) to `.env`. Important settings include:

- `DATABASE_URL`, `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`.
- `JWT_SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `CORS_ORIGINS`.
- `ENABLE_MOCK_ADAPTERS`, `KUBERNETES_IN_CLUSTER`, `KUBECONFIG_PATH`.
- `TRIVY_SERVER_URL`, `TRIVY_SEVERITY_THRESHOLD`.
- `PROMETHEUS_URL`, `GRAFANA_URL`.

Never commit `.env`, kubeconfig contents, registry credentials, or Kubernetes
Secret values.

## Docker Compose

Copy `.env.example` to `.env`, replace local passwords and the JWT secret, and
run:

```powershell
docker compose config
docker compose build
docker compose up -d
docker compose ps
```

The stack starts PostgreSQL with a named persistent volume, runs backend
migrations in the backend container before Uvicorn, and starts the frontend
after backend readiness. The default adapter remains mock mode. The frontend
is at `http://localhost:5173`; the API docs are at
`http://localhost:8000/docs`.

Useful commands:

```powershell
docker compose logs -f backend
docker compose run --rm backend alembic upgrade head
docker compose stop
docker compose down
docker compose down -v  # intentionally removes local database data
```

Monitoring is optional:

```powershell
docker compose --profile monitoring up -d
```

Prometheus is at `http://localhost:9090` and Grafana at
`http://localhost:3000`. Set `GRAFANA_ADMIN_PASSWORD` in `.env`.
See [OBSERVABILITY.md](OBSERVABILITY.md).

## Minikube or kind

For local Kubernetes, build images into the cluster runtime:

```powershell
# Minikube
minikube start
minikube image build -t releasepilot/backend:dev ./backend
minikube image build -t releasepilot/frontend:dev ./frontend

# Or kind
kind create cluster --name releasepilot
docker build -t releasepilot/backend:dev ./backend
docker build -t releasepilot/frontend:dev ./frontend
kind load docker-image releasepilot/backend:dev --name releasepilot
kind load docker-image releasepilot/frontend:dev --name releasepilot
```

Install the chart with a private values file or `--set` values. Do not commit
secret values:

```powershell
helm upgrade --install releasepilot .\infrastructure\helm\releasepilot `
  --namespace releasepilot --create-namespace `
  --set images.backend.repository=releasepilot/backend `
  --set images.backend.tag=dev `
  --set images.frontend.repository=releasepilot/frontend `
  --set images.frontend.tag=dev `
  --set database.enabled=true `
  --set secrets.create=true `
  --set-string secrets.databaseUrl='postgresql+psycopg2://releasepilot:CHANGE_ME@releasepilot-postgres:5432/releasepilot' `
  --set-string secrets.databasePassword='CHANGE_ME' `
  --set-string secrets.jwtSecretKey='CHANGE_ME_LONG_RANDOM_VALUE' `
  --set-string secrets.adminInitialPassword='CHANGE_ME'
```

Validate before applying:

```powershell
helm lint .\infrastructure\helm\releasepilot
helm template releasepilot .\infrastructure\helm\releasepilot `
  --set secrets.create=false `
  --set secrets.existingSecret=releasepilot-secrets
```

See [the chart README](infrastructure/helm/releasepilot/README.md) for
upgrade, rollback, ingress, RBAC, network policy, and capacity guidance.

## Real Kubernetes deployments

To exercise the production adapter, configure a valid cluster context or
in-cluster service account, set `ENABLE_MOCK_ADAPTERS=false`, grant only the
required RBAC, and make the immutable image available to the cluster. The
adapter patches a Deployment and polls readiness; it never runs arbitrary
shell commands or accepts raw kubeconfig content through public API fields.

This path needs external cluster infrastructure and should not be confused
with mock-mode test results. Rolling updates reduce interruption risk but
cannot guarantee zero downtime when readiness probes, database compatibility,
capacity, image availability, or shutdown behavior are incorrect.

## GitHub Actions, registry, and GitOps

The workflows in `.github/workflows` run frontend/backend quality checks,
build immutable commit-SHA images, scan them with Trivy, validate Helm, and
optionally update a separate GitOps repository. Publishing is opt-in.

Configure repository variables such as `CONTAINER_REGISTRY`,
`IMAGE_NAMESPACE`, `BACKEND_IMAGE_NAME`, `FRONTEND_IMAGE_NAME`, and
`PUBLISH_IMAGES`. Store registry credentials in GitHub Actions secrets and
protect the production Environment with required reviewers. CI does not claim
Kubernetes deployment success from an image build.

For Argo CD, configure
[infrastructure/argocd/application.yaml](infrastructure/argocd/application.yaml)
with the GitOps repository and destination. Argo CD owns reconciliation;
CI only changes desired configuration.

## Optional Prometheus, Grafana, and Trivy

Prometheus scrapes `/metrics`. The application exposes request count,
latency, deployment duration, rollout failures, rollback outcomes, and
health-check results. Metrics labelled `simulated="true"` are mock results,
not cluster evidence. Node, Kubernetes, and database exporter metrics are not
provided by the application.

Grafana provisioning and dashboard files are under
`infrastructure/grafana`. Trivy image scans run in CI; local scanning requires
the Trivy CLI, for example:

```powershell
trivy image releasepilot-backend:dev
```

## Tests and validation

```powershell
cd backend
pytest -v
python -m compileall -q app alembic

cd ..\frontend
npm test
npm run build

cd ..
docker compose config
helm lint infrastructure/helm/releasepilot
```

The backend tests use SQLite and mock adapters. They verify authentication,
API behavior, deployment orchestration, rollback behavior, metrics, and
request IDs. Frontend tests are component-level. A live Docker, PostgreSQL,
Kubernetes, Prometheus, Grafana, registry, or Argo CD run requires the
corresponding external service and is not implied by these tests.

## Troubleshooting

- **Port in use:** change `FRONTEND_PORT`, `BACKEND_PORT`, or `POSTGRES_PORT`
  in `.env`, then recreate the affected Compose service.
- **Database not ready:** inspect `docker compose ps` and
  `docker compose logs db`; the backend waits for the database health check.
- **Migration error:** inspect backend logs and run
  `docker compose run --rm backend alembic upgrade head`.
- **Frontend cannot call the API:** verify `http://localhost:8000/health/ready`
  and use `VITE_API_URL=/api/v1` with the provided proxy.
- **Kubernetes unavailable:** restore mock mode for local work. In real mode,
  check kubeconfig/context, namespace, RBAC, image availability, and adapter
  logs.
- **Rollback unavailable:** a previous known-good release is required, and
  readiness/smoke verification must pass for a successful rollback.

## Known limitations and production hardening

- SQLite is for local development/tests; use managed PostgreSQL for shared or
  production deployments.
- Mock deployments and scans are explicitly labelled and do not prove
  Kubernetes or registry health.
- Automatic rollback is not a database rollback. Use backward-compatible
  expand/contract migrations and separate data recovery procedures.
- Replace development JWT/demo credentials, restrict CORS, use HTTPS, protect
  `/metrics` and administrative endpoints, rotate secrets, and configure
  centralized log retention before production.
- Run dependency, code, and image security scans and require protected
  production approvals.
