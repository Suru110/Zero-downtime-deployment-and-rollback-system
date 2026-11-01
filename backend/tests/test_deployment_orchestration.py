import pytest
from app.services.deployment_engine import DeploymentEngine
from app.models.deployment import Deployment
from app.models.environment import Environment
from app.models.rollback import RollbackEvent

@pytest.mark.asyncio
async def test_successful_deployment_pipeline(client, db_session, admin_token_headers):
    # 1. Setup Project & Environment
    proj_resp = client.post("/api/v1/projects", json={
        "name": "catalog-service",
        "git_repo": "https://github.com/org/catalog-service.git",
        "image_repository": "docker.io/releasepilot/catalog-service",
        "default_port": 8080,
        "health_path": "/healthz"
    }, headers=admin_token_headers)
    proj_id = proj_resp.json()["data"]["id"]

    env_resp = client.post(f"/api/v1/projects/{proj_id}/environments", json={
        "name": "staging",
        "k8s_namespace": "catalog-staging",
        "replicas": 2,
        "deployment_strategy": "rolling",
        "auto_rollback_enabled": True
    }, headers=admin_token_headers)
    env_id = env_resp.json()["data"]["id"]

    # 2. Setup Release
    rel_resp = client.post(f"/api/v1/projects/{proj_id}/releases", json={
        "version": "v1.0.0",
        "git_commit": "1111222233334444555566667777888899990000",
        "image_tag": "v1.0.0"
    }, headers=admin_token_headers)
    rel_id = rel_resp.json()["data"]["id"]

    # 3. Trigger Deployment via API
    dep_resp = client.post("/api/v1/deployments", json={
        "project_id": proj_id,
        "environment_id": env_id,
        "release_id": rel_id,
        "simulate_failure": False
    }, headers=admin_token_headers)
    assert dep_resp.status_code == 202
    dep_id = dep_resp.json()["data"]["id"]

    # Execute pipeline synchronously for verification
    await DeploymentEngine.execute_deployment(db=db_session, deployment_id=dep_id, simulate_failure=False)

    # 4. Verify deployment state in DB
    dep = db_session.query(Deployment).filter(Deployment.id == dep_id).first()
    assert dep.status == "active"
    assert dep.progress == 100
    assert len(dep.logs) > 0

    env = db_session.query(Environment).filter(Environment.id == env_id).first()
    assert env.current_release_id == rel_id

@pytest.mark.asyncio
async def test_automated_rollback_on_health_check_failure(client, db_session, admin_token_headers):
    # Setup Project & Environment
    proj_resp = client.post("/api/v1/projects", json={
        "name": "billing-service",
        "git_repo": "https://github.com/org/billing-service.git",
        "image_repository": "docker.io/releasepilot/billing-service",
        "default_port": 8080,
        "health_path": "/healthz"
    }, headers=admin_token_headers)
    proj_id = proj_resp.json()["data"]["id"]

    env_resp = client.post(f"/api/v1/projects/{proj_id}/environments", json={
        "name": "production",
        "k8s_namespace": "billing-prod",
        "replicas": 3,
        "deployment_strategy": "rolling",
        "auto_rollback_enabled": True
    }, headers=admin_token_headers)
    env_id = env_resp.json()["data"]["id"]

    # Create known-good release v1.0.0 and deploy
    rel1_resp = client.post(f"/api/v1/projects/{proj_id}/releases", json={
        "version": "v1.0.0",
        "git_commit": "aaaa1111bbbb2222cccc3333dddd4444eeee5555",
        "image_tag": "v1.0.0"
    }, headers=admin_token_headers)
    rel1_id = rel1_resp.json()["data"]["id"]

    dep1_resp = client.post("/api/v1/deployments", json={
        "project_id": proj_id,
        "environment_id": env_id,
        "release_id": rel1_id
    }, headers=admin_token_headers)
    dep1_id = dep1_resp.json()["data"]["id"]
    await DeploymentEngine.execute_deployment(db=db_session, deployment_id=dep1_id, simulate_failure=False)

    # Now create buggy release v1.1.0 and deploy with simulate_failure=True
    rel2_resp = client.post(f"/api/v1/projects/{proj_id}/releases", json={
        "version": "v1.1.0",
        "git_commit": "ffff6666aaaa1111bbbb2222cccc3333dddd4444",
        "image_tag": "v1.1.0"
    }, headers=admin_token_headers)
    rel2_id = rel2_resp.json()["data"]["id"]

    dep2_resp = client.post("/api/v1/deployments", json={
        "project_id": proj_id,
        "environment_id": env_id,
        "release_id": rel2_id,
        "simulate_failure": True
    }, headers=admin_token_headers)
    dep2_id = dep2_resp.json()["data"]["id"]

    # Drive pipeline failure
    await DeploymentEngine.execute_deployment(db=db_session, deployment_id=dep2_id, simulate_failure=True)

    # Verify that deployment was marked rolled_back and environment reverted to v1.0.0!
    dep2 = db_session.query(Deployment).filter(Deployment.id == dep2_id).first()
    assert dep2.status == "rolled_back"

    env = db_session.query(Environment).filter(Environment.id == env_id).first()
    assert env.current_release_id == rel1_id

    # Check RollbackEvent record
    rb_event = db_session.query(RollbackEvent).filter(RollbackEvent.source_deployment_id == dep2_id).first()
    assert rb_event is not None
    assert rb_event.failed_release_id == rel2_id
    assert rb_event.restored_release_id == rel1_id
    assert rb_event.is_automated is True
