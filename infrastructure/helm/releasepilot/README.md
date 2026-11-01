# ReleasePilot Helm chart

This chart deploys the frontend and FastAPI backend to Minikube, kind, or a
generic Kubernetes cluster. PostgreSQL is disabled by default because a
managed production database is preferred. Set `database.enabled=true` only for
local/demo clusters.

## Local Minikube or kind

Build images into the cluster runtime, then install the chart. The image
repository and tag values must match the images built or loaded into the
cluster.

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

Create a private values file or supply secrets at install time. Do not commit
that file:

```powershell
helm upgrade --install releasepilot .\infrastructure\helm\releasepilot `
  --namespace releasepilot --create-namespace `
  --set images.backend.repository=releasepilot/backend `
  --set images.backend.tag=dev `
  --set images.frontend.repository=releasepilot/frontend `
  --set images.frontend.tag=dev `
  --set database.enabled=true `
  --set secrets.create=true `
  --set-string secrets.databaseUrl='postgresql+psycopg2://releasepilot:CHANGE_ME@releasepilot-releasepilot-postgres:5432/releasepilot' `
  --set-string secrets.databasePassword='CHANGE_ME' `
  --set-string secrets.jwtSecretKey='CHANGE_ME_LONG_RANDOM_VALUE' `
  --set-string secrets.adminInitialPassword='CHANGE_ME'
```

The backend container runs `alembic upgrade head` before Uvicorn starts. The
local PostgreSQL StatefulSet uses a PVC when the cluster has a default
StorageClass; set `database.persistence.storageClass` when it does not.

## Validation

```powershell
helm lint .\infrastructure\helm\releasepilot
helm template releasepilot .\infrastructure\helm\releasepilot `
  --set secrets.create=false `
  --set secrets.existingSecret=releasepilot-secrets
helm template releasepilot .\infrastructure\helm\releasepilot `
  --set database.enabled=true `
  --set secrets.create=true `
  --set-string secrets.databaseUrl='postgresql+psycopg2://releasepilot:CHANGE_ME@releasepilot-releasepilot-postgres:5432/releasepilot' `
  --set-string secrets.databasePassword=CHANGE_ME `
  --set-string secrets.jwtSecretKey=CHANGE_ME_LONG_RANDOM_VALUE `
  --set-string secrets.adminInitialPassword=CHANGE_ME `
  | kubectl apply --dry-run=client -f -
```

The chart requires Helm 3 and a Kubernetes cluster version supporting
`apps/v1`, `policy/v1`, `autoscaling/v2`, and `networking.k8s.io/v1`.

## Operations

```powershell
kubectl -n releasepilot get pods,svc,pvc
kubectl -n releasepilot rollout status deployment/releasepilot-releasepilot-backend
kubectl -n releasepilot rollout undo deployment/releasepilot-releasepilot-backend
helm history releasepilot -n releasepilot
helm rollback releasepilot <REVISION> -n releasepilot
kubectl -n releasepilot logs deploy/releasepilot-releasepilot-backend
```

Enable the optional Ingress with `--set ingress.enabled=true` and configure an
Ingress controller. Minikube users can run `minikube addons enable ingress` and
map the configured host to the Minikube IP. kind users need an ingress
controller and host port mappings.

Rolling updates use configurable `maxSurge` and `maxUnavailable` values. They
reduce interruption risk but cannot guarantee zero downtime when readiness
probes, database compatibility, capacity, image availability, or application
shutdown behavior are incorrect. Run with at least two backend/frontend
replicas and enough spare CPU/memory for the configured surge.

RBAC is namespace-scoped by default. The backend receives only deployment and
pod read/write visibility when `backend.rbac.deploymentReadWrite=true`, which
is needed by the Kubernetes adapter. Set `backend.rbac.clusterWide=true` only
when the backend deploys to multiple namespaces; this creates a
ClusterRole/ClusterRoleBinding with the same narrow resource verbs. Set
`deploymentReadWrite=false` if deployments are performed through GitOps and
the backend does not need Kubernetes write access.
NetworkPolicy is disabled by default because cluster CNI support varies; enable
it only after adapting egress rules for the cluster's DNS and integration
endpoints.
