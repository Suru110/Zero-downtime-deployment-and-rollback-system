# ReleasePilot Architecture Document

## 1. System Overview
**ReleasePilot** is a production-oriented zero-downtime deployment and automated rollback platform designed for modern containerized cloud-native microservices. It orchestrates deployments across multiple environments (development, staging, production) with progressive release strategies (Kubernetes Rolling Updates, Canary Deployments, GitOps via Argo CD), continuous synthetic health verifications, and automated fail-safe rollback to known-good releases.

## 2. High-Level Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                                  ReleasePilot Web UI                              |
|                      (React + TypeScript + Vite + Tailwind CSS)                   |
+-----------------------------------------+-----------------------------------------+
                                          | REST API (JWT Authenticated)
                                          v
+-----------------------------------------------------------------------------------+
|                             ReleasePilot Backend (FastAPI)                        |
|                                                                                   |
|  +-------------------+  +-------------------+  +-------------------------------+  |
|  | Auth & RBAC       |  | App & Environment |  | Release & Config Registry     |  |
|  | (Admin/Dev/Viewer)|  | Management        |  | (Semver, Digest, Git Commit)   |  |
|  +-------------------+  +-------------------+  +-------------------------------+  |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  |                           Deployment Orchestrator                           |  |
|  |  +-------------------------+  +-------------------+  +--------------------+ |  |
|  |  | Rolling Deployment Engine|  | Canary Controller |  | Rollback Engine    | |  |
|  |  +-------------------------+  +-------------------+  +--------------------+ |  |
|  +-----------------------------------------------------------------------------+  |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  |                              Pluggable Adapters                             |  |
|  |  +-------------------+  +-------------------+  +--------------------------+ |  |
|  |  | Kubernetes Adapter|  | GitOps (Argo CD)  |  | Security Scanner (Trivy) | |  |
|  |  | (Real / Local K8s)|  | (Real / Mock)     |  | (Real CLI / Mock)        | |  |
|  |  +-------------------+  +-------------------+  +--------------------------+ |  |
|  |  +------------------------------------------+  +--------------------------+ |  |
|  |  | Health & Metric Prober (Prometheus/HTTP) |  | Structured Audit Logger  | |  |
|  |  +------------------------------------------+  +--------------------------+ |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------+-----------------------------------------+
                                          |
                         +----------------+----------------+
                         |                                 |
                         v                                 v
              +--------------------+             +-------------------+
              |  PostgreSQL / DB   |             | Target Kubernetes |
              | (State & Auditing) |             | (Minikube / Kind) |
              +--------------------+             +-------------------+
```

## 3. Core Entities & Relational Schema
1. **User**: Represents platform users with roles (`admin`, `operator`, `developer`, `viewer`) and bcrypt-hashed credentials.
2. **Project / Application**: Multi-tenant application definitions with Git repo URL, container image registry path, default port, health check path, and ownership.
3. **Environment**: Deployment targets (e.g. `dev`, `staging`, `production`) attached to a project, defining cluster namespace, replica count, environment variables, strategy (`rolling` or `canary`), and auto-rollback configuration.
4. **Release**: Immutable build artifact metadata representing an application version (git commit SHA, image tag, semver, configuration hash, Trivy vulnerability scan status).
5. **Deployment**: An execution instance deploying a specific Release to an Environment. Tracks phases: `pending`, `scanning`, `deploying`, `verifying`, `active`, `failed`, `rolled_back`.
6. **HealthCheck**: Structured test runs (Readiness probe, HTTP endpoint smoke tests, metrics check) executed post-deployment.
7. **RollbackEvent**: Automated or manual rollback records indicating root cause, triggering health failure, source deployment, and restored target release.
8. **AuditLog**: Tamper-evident operational logs tracking actor, action, timestamp, target entity, and IP address.

## 4. Zero-Downtime & Automated Rollback Mechanics
- **Rolling Strategy**: Provisions updated pods using Kubernetes native `maxSurge` (25%) and `maxUnavailable` (0) to ensure zero dropped packets during rollout.
- **Canary Strategy**: Directs a configurable percentage of traffic (e.g. 10% -> 25% -> 50% -> 100%) to the canary replica set while monitoring latency and error rates.
- **Health Verification Cycle**:
  1. Kubernetes readiness probe check.
  2. Configurable HTTP smoke tests against ingress/service.
  3. Prometheus metric error rate check (e.g., HTTP 5xx rate < 1%).
- **Rollback Trigger**:
  If any health verification fails within the verification window (or if pod crashes occur), the orchestrator immediately triggers an automated rollback to the last verified release (`current_release_id` of Environment) and marks the deployment as `failed` with a comprehensive `RollbackEvent`.

## 5. Adapter Architecture & Simulation Integrity
In accordance with platform guidelines:
- Adapters follow strict abstract base interfaces:
  - `DeploymentAdapter`: interface for executing rolling/canary rollouts and querying status.
  - `GitOpsAdapter`: interface for syncing Argo CD applications.
  - `SecurityScannerAdapter`: interface for image vulnerability scanning.
  - `MetricsAdapter`: interface for querying Prometheus metrics.
- Each adapter has two implementations:
  1. **Production / Live Adapter**: Connects to Kubernetes API (via `kubernetes` Python client or `kubectl`), Argo CD REST API, Trivy CLI/server, and Prometheus HTTP API.
  2. **Mock / Simulation Adapter**: Operates without external infrastructure for self-contained testing and deterministic CI, explicitly labeling all outcomes with `is_simulated: true` and simulation telemetry.
- **Honesty Rule**: The platform never reports simulated runs as real cluster executions.
