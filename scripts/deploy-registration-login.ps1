$ErrorActionPreference = "Stop"

$image = "docker.io/surabhi1106/registration-login:v1.0.0"
docker pull $image
if ($LASTEXITCODE -ne 0) {
  Write-Warning "Image $image was not found in Docker Hub; building the checked-out application into Minikube."
  minikube image build -t $image Registration-login
  if ($LASTEXITCODE -ne 0) {
    throw "Docker image pull and Minikube image build both failed."
  }
}
kubectl config use-context minikube
if ($LASTEXITCODE -ne 0) {
  throw "The minikube kubectl context is unavailable."
}
kubectl cluster-info --context minikube
if ($LASTEXITCODE -ne 0) {
  throw "The Minikube Kubernetes API is unavailable. Start Minikube and retry."
}
kubectl apply -f Registration-login\k8s\registration-login.yaml
if ($LASTEXITCODE -ne 0) {
  throw "Kubernetes manifest application failed."
}
kubectl rollout status deployment/registration-login -n registration-login-staging --timeout=180s

$pod = kubectl get pods -n registration-login-staging -l app=registration-login -o jsonpath="{.items[0].metadata.name}"
kubectl get pods -n registration-login-staging -o wide
kubectl logs -n registration-login-staging $pod --tail=100

kubectl exec -n registration-login-staging $pod -- node -e "const http=require('http'); http.get('http://127.0.0.1:3000/healthz',r=>{console.log('healthz='+r.statusCode); process.exit(r.statusCode===200?0:1)}).on('error',e=>{console.error(e.message);process.exit(1)})"
kubectl exec -n registration-login-staging $pod -- node -e "const http=require('http'); http.get('http://127.0.0.1:3000/readyz',r=>{console.log('readyz='+r.statusCode); process.exit(r.statusCode===200?0:1)}).on('error',e=>{console.error(e.message);process.exit(1)})"
kubectl exec -n registration-login-staging $pod -- node -e "const http=require('http'); http.get('http://127.0.0.1:3000/livez',r=>{console.log('livez='+r.statusCode); process.exit(r.statusCode===200?0:1)}).on('error',e=>{console.error(e.message);process.exit(1)})"
