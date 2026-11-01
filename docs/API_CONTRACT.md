# ReleasePilot API Contract (v1)

Base URL: `/api/v1`

All responses follow a consistent schema. Errors return standardized error objects.

```json
{
  "success": true,
  "data": { ... },
  "message": "Optional message"
}
```

Error response:
```json
{
  "success": false,
  "error": {
    "code": "ENTITY_NOT_FOUND",
    "message": "Application with id '123' not found",
    "details": {}
  }
}
```

---

## 1. Authentication (`/auth`)

### `POST /auth/register`
- **Request**:
  ```json
  {
    "username": "developer1",
    "email": "dev@releasepilot.local",
    "password": "StrongPassword123!",
    "role": "developer" // admin | operator | developer | viewer
  }
  ```
- **Response (201)**:
  ```json
  {
    "id": "usr_01H...",
    "username": "developer1",
    "email": "dev@releasepilot.local",
    "role": "developer",
    "created_at": "2026-10-29T08:00:00Z"
  }
  ```

### `POST /auth/login`
- **Request** (`application/x-www-form-urlencoded` or JSON):
  ```json
  {
    "username": "developer1",
    "password": "StrongPassword123!"
  }
  ```
- **Response (200)**:
  ```json
  {
    "access_token": "eyJhbG...",
    "token_type": "bearer",
    "expires_in": 86400,
    "user": {
      "id": "usr_01H...",
      "username": "developer1",
      "email": "dev@releasepilot.local",
      "role": "developer"
    }
  }
  ```

### `GET /auth/me`
- **Headers**: `Authorization: Bearer <token>`
- **Response (200)**: User profile details.

---

## 2. Projects / Applications (`/projects`)

### `GET /projects`
- Query Params: `skip=0`, `limit=50`, `search=...`
- Returns array of projects with summarized environment and release status.

### `POST /projects`
- **Request**:
  ```json
  {
    "name": "payment-service",
    "description": "Core payment processing service",
    "git_repo": "https://github.com/org/payment-service.git",
    "default_branch": "main",
    "image_repository": "docker.io/releasepilot/payment-service",
    "default_port": 8080,
    "health_path": "/healthz"
  }
  ```

### `GET /projects/{project_id}`
- Detailed project profile including all environments, releases, and recent deployments.

### `PUT /projects/{project_id}`
- Update project configuration.

### `DELETE /projects/{project_id}`
- Delete project (Admin/Operator only).

---

## 3. Environments (`/projects/{project_id}/environments`)

### `GET /projects/{project_id}/environments`
- List all configured environments for a project (e.g. dev, staging, prod).

### `POST /projects/{project_id}/environments`
- **Request**:
  ```json
  {
    "name": "production",
    "k8s_namespace": "payment-prod",
    "k8s_cluster": "minikube-local",
    "replicas": 3,
    "deployment_strategy": "rolling", // rolling | canary
    "canary_steps": [10, 25, 50, 100],
    "auto_rollback_enabled": true,
    "verification_timeout_seconds": 60,
    "smoke_test_endpoint": "/api/v1/ping",
    "env_vars": {
      "NODE_ENV": "production",
      "LOG_LEVEL": "info"
    }
  }
  ```

### `PUT /projects/{project_id}/environments/{environment_id}`
- Update environment settings.

---

## 4. Releases (`/projects/{project_id}/releases`)

### `POST /projects/{project_id}/releases`
- Registers a new immutable release artifact.
- **Request**:
  ```json
  {
    "version": "v1.4.0",
    "git_commit": "a1b2c3d4e5f678901234567890abcdef12345678",
    "git_branch": "main",
    "image_tag": "v1.4.0",
    "commit_message": "Add idempotency headers to payment processing",
    "changelog": "Fix race conditions and optimize latency."
  }
  ```

### `GET /projects/{project_id}/releases`
- List releases with vulnerability scan status (`clean`, `warning`, `critical`, `pending`).

### `POST /projects/{project_id}/releases/{release_id}/scan`
- Triggers Trivy security vulnerability scan. Returns scan breakdown (Critical, High, Medium, Low).

---

## 5. Deployments (`/deployments`)

### `POST /deployments`
- Trigger deployment of a Release to an Environment.
- **Request**:
  ```json
  {
    "project_id": "prj_01H...",
    "environment_id": "env_01H...",
    "release_id": "rel_01H...",
    "override_strategy": null,
    "dry_run": false
  }
  ```
- **Response (202 Accepted)**:
  ```json
  {
    "deployment_id": "dep_01H...",
    "status": "pending",
    "created_at": "2026-10-29T08:00:00Z"
  }
  ```

### `GET /deployments/{deployment_id}`
- Status (`pending`, `scanning`, `deploying`, `verifying`, `active`, `failed`, `rolled_back`), logs, health checks, execution mode (`real` or `simulated`), and adapter details.

### `GET /deployments/{deployment_id}/logs`
- Step-by-step real-time deployment logs.

### `POST /deployments/{deployment_id}/cancel`
- Aborts an in-flight deployment.

---

## 6. Health Checks & Verification (`/deployments/{deployment_id}/health-checks`)

### `GET /deployments/{deployment_id}/health-checks`
- Returns array of health verification attempts:
  - Pod readiness check
  - HTTP smoke test response code and latency
  - Prometheus error-rate metric probe

---

## 7. Rollbacks (`/rollbacks`)

### `POST /rollbacks`
- Trigger manual rollback or inspect automated rollback.
- **Request**:
  ```json
  {
    "deployment_id": "dep_01H...",
    "reason": "Elevated 502 Bad Gateway responses detected post-release"
  }
  ```
- **Response (200)**:
  ```json
  {
    "rollback_id": "rbk_01H...",
    "target_release_id": "rel_previous",
    "status": "completed",
    "restored_at": "2026-10-29T08:02:15Z"
  }
  ```

---

## 8. Metrics & Observability (`/metrics`)

### `GET /metrics/deployment-stats`
- System-wide deployment velocity, success rate, mean time to recovery (MTTR), and active releases.

### `GET /projects/{project_id}/environments/{environment_id}/metrics`
- Live Prometheus telemetry (pod CPU, memory, request count, HTTP 5xx rate).

---

## 9. Audit Logs (`/audit-logs`)

### `GET /audit-logs`
- Query system-wide actions by actor, action type, project, and date range.
