# Production Deployment

This repository now includes production deployment assets for:

- Assistant engine (`friday.assistant_engine.service`)
- API backend (FastAPI/Uvicorn)
- Frontend dashboard (React + Nginx reverse proxy)

## Docker Images

- `Dockerfile.api`
- `Dockerfile.engine`
- `Dockerfile.dashboard`

Build locally:

```powershell
docker build -f Dockerfile.api -t friday-api:local .
docker build -f Dockerfile.engine -t friday-engine:local .
docker build -f Dockerfile.dashboard -t friday-dashboard:local .
```

## Docker Compose

Use `docker-compose.yml` to run all services together with shared persistent storage:

```powershell
docker compose up -d --build
```

Endpoints:

- Dashboard: `http://127.0.0.1:8080`
- API docs: `http://127.0.0.1:8000/docs`

Optional image naming overrides:

- `GHCR_OWNER` (default `friday-local`)
- `FRIDAY_IMAGE_TAG` (default `local`)

## Kubernetes

You have two Kubernetes options:

1. **Recommended:** Helm chart (`deploy/helm/friday`)
2. Kustomize manifests (`deploy/k8s`) as static fallback

### Helm (recommended)

Default values:

- `deploy/helm/friday/values.yaml`
- `deploy/helm/values-staging.yaml`
- `deploy/helm/values-production.yaml`

Install staging:

```powershell
helm upgrade --install friday deploy/helm/friday `
  --namespace friday-staging `
  --create-namespace `
  --values deploy/helm/values-staging.yaml `
  --set global.ghcrOwner=<github-org-or-user> `
  --set global.imageTag=sha-<commit-sha> `
  --set auth.username=admin `
  --set auth.password=<staging-password> `
  --set auth.secret=<staging-secret>
```

Install production:

```powershell
helm upgrade --install friday deploy/helm/friday `
  --namespace friday-production `
  --create-namespace `
  --values deploy/helm/values-production.yaml `
  --set global.ghcrOwner=<github-org-or-user> `
  --set global.imageTag=sha-<commit-sha> `
  --set auth.username=admin `
  --set auth.password=<production-password> `
  --set auth.secret=<production-secret>
```

### Kustomize fallback

```powershell
kubectl apply -k deploy/k8s
```

## GitHub Actions

- `CI`: `.github/workflows/ci.yml`
  - Python tests
  - Dashboard build
  - Helm chart lint
- `CD`: `.github/workflows/cd.yml`
  - Build/push `friday-api`, `friday-engine`, `friday-dashboard` images to GHCR
  - Staging deploy with Helm (`staging` environment)
  - Production deploy with Helm (`production` environment, manual dispatch)

### Required secrets for CD

Staging:

- `KUBE_CONFIG_STAGING`
- `FRIDAY_DASHBOARD_AUTH_PASSWORD_STAGING`
- `FRIDAY_DASHBOARD_AUTH_SECRET_STAGING`

Production:

- `KUBE_CONFIG_PRODUCTION`
- `FRIDAY_DASHBOARD_AUTH_PASSWORD_PRODUCTION`
- `FRIDAY_DASHBOARD_AUTH_SECRET_PRODUCTION`

Optional:

- `FRIDAY_DASHBOARD_AUTH_USERNAME_STAGING` / `FRIDAY_DASHBOARD_AUTH_USERNAME_PRODUCTION` (defaults to `admin`)
- `FRIDAY_ENGINE_CLOUD_LLM_API_KEY_STAGING` / `FRIDAY_ENGINE_CLOUD_LLM_API_KEY_PRODUCTION`

## First Deployment Commands (End-to-End)

1. Build/push images from local machine:

```powershell
$tag = "sha-$(git rev-parse --short HEAD)"
$owner = "<github-org-or-user>"
docker build -f Dockerfile.api -t ghcr.io/$owner/friday-api:$tag .
docker build -f Dockerfile.engine -t ghcr.io/$owner/friday-engine:$tag .
docker build -f Dockerfile.dashboard -t ghcr.io/$owner/friday-dashboard:$tag .
docker push ghcr.io/$owner/friday-api:$tag
docker push ghcr.io/$owner/friday-engine:$tag
docker push ghcr.io/$owner/friday-dashboard:$tag
```

2. Deploy to staging with Helm:

```powershell
helm upgrade --install friday deploy/helm/friday `
  --namespace friday-staging `
  --create-namespace `
  --values deploy/helm/values-staging.yaml `
  --set global.ghcrOwner=$owner `
  --set global.imageTag=$tag `
  --set auth.username=admin `
  --set auth.password="<staging-password>" `
  --set auth.secret="<staging-secret>" `
  --wait
```

3. Verify rollout:

```powershell
kubectl -n friday-staging get pods
kubectl -n friday-staging rollout status deployment/friday-friday-api
kubectl -n friday-staging rollout status deployment/friday-friday-engine
kubectl -n friday-staging rollout status deployment/friday-friday-dashboard
```
