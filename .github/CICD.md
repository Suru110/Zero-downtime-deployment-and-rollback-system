# ReleasePilot CI/CD

The pipeline is intentionally split into quality, image, and GitOps stages:

1. `reusable-quality.yml` installs backend/frontend dependencies, runs
   critical-error Python linting, backend tests, the frontend TypeScript
   type-check/build and tests, and lints/renders the Helm chart. The frontend
   currently has no separate ESLint configuration; its TypeScript compiler
   check is the enforced static quality gate.
2. `reusable-images.yml` builds backend and frontend images, tags them with
   `${GITHUB_SHA}`, and scans both images with Trivy. A failed high or critical
   vulnerability scan fails the job.
3. `reusable-gitops-update.yml` is opt-in. It updates image repository/tag
   values in a separate GitOps repository and pushes a commit for Argo CD to
   reconcile. CI does not apply Kubernetes resources and does not report a
   deployment as successful.

## Registry configuration

Set repository or organization variables:

- `CONTAINER_REGISTRY`, for example `ghcr.io`.
- `IMAGE_NAMESPACE`, for example `example-org`.
- `BACKEND_IMAGE_NAME`, optional, default `releasepilot-backend`.
- `FRONTEND_IMAGE_NAME`, optional, default `releasepilot-frontend`.
- `PUBLISH_IMAGES=true` to publish on pushes to configured branches.

For registries requiring explicit credentials, add environment/repository
secrets:

- `REGISTRY_USERNAME`
- `REGISTRY_PASSWORD`

The workflow fails rather than attempting a publish when these values are
missing. Prefer a registry's OIDC or GitHub App short-lived token flow when
available. GitHub-hosted private image publishing can instead be implemented
with a narrowly scoped `GITHUB_TOKEN` configuration.

## Environments and production protection

Use separate GitHub Environments named `dev`, `staging`, and `production`.
Configure required reviewers and branch restrictions on `production`. The
workflow only updates GitOps when manually dispatched with an environment
selected; production therefore requires an explicit dispatch plus the
environment's approval gate. Do not set automatic production promotion.

## Argo CD GitOps

The example manifest is
[infrastructure/argocd/application.yaml](../infrastructure/argocd/application.yaml).
Copy it to a GitOps repository and replace `repoURL`, `path`, and the target
cluster details. The example values file is
[infrastructure/gitops/environments/dev/values.yaml](../infrastructure/gitops/environments/dev/values.yaml).

To enable the opt-in update job, configure:

- Repository variable `GITOPS_REPOSITORY` as `owner/repository`.
- Repository variable `GITOPS_REF`, normally `main`.
- Repository variable `GITOPS_VALUES_FILE`.
- Secret `GH_PAT` with least-privilege contents read/write access to the GitOps
  repository.

Argo CD must be installed and have access to the GitOps repository. Argo CD,
not GitHub Actions, owns Kubernetes reconciliation. CI only changes desired
image configuration after tests and scans pass.

Example environment files are provided under
`infrastructure/gitops/environments/{dev,staging,production}`. Keep the
production environment protected in GitHub and require an approval before
running its GitOps update.

## Local validation

```powershell
actionlint
helm lint .\infrastructure\helm\releasepilot
helm template releasepilot .\infrastructure\helm\releasepilot `
  --set secrets.create=false `
  --set secrets.existingSecret=releasepilot-secrets
```

Install `actionlint` locally to validate workflow expressions. The workflow
does not require AWS or any cloud provider. Publishing and GitOps updates are
disabled unless explicitly configured.
