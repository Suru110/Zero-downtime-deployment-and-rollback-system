# ReleasePilot backend

## Local setup

Create a virtual environment, install `requirements.txt`, copy the repository
`.env.example` to `.env`, and run:

```bash
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

The default configuration uses the simulated adapters. Set
`KUBERNETES_MODE=production` to use the configured Kubernetes context, or
explicitly set `KUBERNETES_MODE=mock` for simulated deployments. Keep
`ENABLE_MOCK_ADAPTERS=true` unless Trivy, Argo CD, and Prometheus endpoints are
also configured; this setting does not select the Kubernetes adapter. Simulated
responses are marked with
`is_simulated=true` and are never presented as live cluster results.

Swagger's **Authorize** dialog submits the OAuth2 form to
`POST /api/v1/auth/token`, using the account email as `username`. The JSON
login endpoint remains available at `POST /api/v1/auth/login`.

In production mode, a rollout is only reported as active after Kubernetes
readiness and public HTTP endpoint verification succeed. For optional
Cloudflare Quick Tunnels, enable `CLOUDFLARE_TUNNEL_ENABLED` and configure
`CLOUDFLARED_PATH` and `KUBECTL_PATH` on the backend host. Quick Tunnel URLs
are temporary and rely on the local port-forward and tunnel processes remaining
alive; use a stable Ingress or LoadBalancer endpoint for production.

For the local `Registration-login` application, register the image with port
`3000` and health path `/healthz`. Its SQLite database is stored inside the
container at `/app/data/users.db`; use one replica unless a persistent-volume
and single-writer policy are configured.

Users are created through `POST /api/v1/auth/register` or the frontend
registration page. The backend does not create administrator, developer, or
demo accounts during startup. The optional seed command only creates sample
deployment data and never creates user accounts.
