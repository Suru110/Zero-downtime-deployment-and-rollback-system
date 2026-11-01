def test_create_project_and_environments(client, admin_token_headers):
    # 1. Create Project
    proj_payload = {
        "name": "cart-service",
        "description": "High performance cart microservice",
        "git_repo": "https://github.com/org/cart-service.git",
        "default_branch": "main",
        "image_repository": "docker.io/releasepilot/cart-service",
        "default_port": 8080,
        "health_path": "/healthz"
    }
    resp = client.post("/api/v1/projects", json=proj_payload, headers=admin_token_headers)
    assert resp.status_code == 201
    proj_data = resp.json()["data"]
    proj_id = proj_data["id"]
    assert proj_data["name"] == "cart-service"

    # 2. Create Environment
    env_payload = {
        "name": "production",
        "k8s_namespace": "cart-prod",
        "k8s_cluster": "default",
        "replicas": 3,
        "deployment_strategy": "rolling",
        "auto_rollback_enabled": True,
        "verification_timeout_seconds": 60,
        "smoke_test_endpoint": "/healthz",
        "env_vars": {"REDIS_URL": "redis://cache:6379"}
    }
    resp_env = client.post(f"/api/v1/projects/{proj_id}/environments", json=env_payload, headers=admin_token_headers)
    assert resp_env.status_code == 201
    env_data = resp_env.json()["data"]
    assert env_data["name"] == "production"
    assert env_data["k8s_namespace"] == "cart-prod"

    # 3. List Environments
    resp_list = client.get(f"/api/v1/projects/{proj_id}/environments", headers=admin_token_headers)
    assert resp_list.status_code == 200
    assert len(resp_list.json()["data"]) == 1
