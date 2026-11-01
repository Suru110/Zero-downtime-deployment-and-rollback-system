# ReleasePilot observability and security

## What is collected

The backend exposes Prometheus metrics at `/metrics`. These are application
metrics, not node, container, Kubernetes, or database exporter metrics:

- `releasepilot_http_requests_total` and
  `releasepilot_http_request_duration_seconds`: request count, status, and
  latency by method and route.
- `releasepilot_deployment_duration_seconds`: deployment duration by strategy
  and terminal status.
- `releasepilot_rollout_failures_total`: rollout failures reported by an
  adapter, labelled as simulated or live.
- `releasepilot_rollbacks_total`: rollback outcome, automation mode, and
  simulated/live adapter.
- `releasepilot_health_checks_total`: readiness, smoke-test, and metric-check
  results, including whether the adapter was simulated.

Metrics labelled `simulated="true"` come from the mock adapter and must not be
used as evidence of cluster health. Kubernetes, database, and host metrics are
unavailable unless separate exporters are installed.

`/health/live` only proves that the process is responding. `/health/ready`
also checks database connectivity and returns HTTP 503 when the database is
unavailable. `/metrics` is intentionally unauthenticated for Prometheus
scraping; restrict it at the ingress or network layer in production.

## Optional local monitoring

Monitoring is not required for the normal application profile:

```powershell
docker compose --profile monitoring up -d
docker compose --profile monitoring ps
```

Prometheus is available at `http://localhost:9090`; Grafana is available at
`http://localhost:3000`. Set `GRAFANA_ADMIN_PASSWORD` in `.env` before
starting the profile. The provisioned dashboard is **ReleasePilot Overview**.
Prometheus loads alert examples for rollout failures, sustained HTTP errors,
and failed rollbacks.

Stop only the optional services with:

```powershell
docker compose --profile monitoring stop prometheus grafana
```

## Logging and request correlation

Application logs are JSON with UTC timestamps, levels, logger names, and
redacted context. Requests receive an `X-Request-ID` response header; a caller
supplied value is preserved for correlation. Deployment execution logs include
the deployment ID. Passwords, tokens, authorization headers, secrets, and
kubeconfig-related fields are redacted.

Send container stdout/stderr to the platform log collector. Keep production
logs according to the organization's retention policy; a 30-day starting point
is reasonable for operational troubleshooting, subject to compliance and cost
requirements. Do not put access tokens or raw Kubernetes API errors containing
credentials into log aggregation.

## Security checklist

- Keep `.env`, registry credentials, JWT secrets, kubeconfig files, and
  Kubernetes Secret values outside source control.
- Use a strong production `JWT_SECRET_KEY`, restricted CORS origins, and
  HTTPS at the ingress.
- Run application containers as non-root and use the least-privilege
  Kubernetes service account/RBAC supplied by the Helm chart.
- Run `pip-audit` and Bandit in CI and treat failures as release blockers.
- Trivy scans both application images and fail on the configured severity
  threshold (`HIGH,CRITICAL` by default).
- Use immutable image tags or digests and require protected environment
  approval before production changes.
- Review audit events for deployments, rollbacks, configuration changes, and
  administrative operations.
- Protect `/metrics`, `/docs`, and administrative endpoints at the production
  ingress or network boundary as appropriate.

## Validation

Without Docker or a live cluster, only application metrics and configuration
syntax can be validated locally. A live Prometheus scrape, Grafana rendering,
container scan, and Kubernetes telemetry require their respective services
and are not represented as available when they are not running.
