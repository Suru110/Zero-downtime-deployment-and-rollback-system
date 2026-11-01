def test_release_lifecycle_and_scan(client, admin_token_headers):
    # Create project
    proj_resp = client.post("/api/v1/projects", json={
        "name": "auth-service",
        "git_repo": "https://github.com/org/auth-service.git",
        "image_repository": "docker.io/releasepilot/auth-service",
        "default_port": 8000,
        "health_path": "/health"
    }, headers=admin_token_headers)
    proj_id = proj_resp.json()["data"]["id"]

    # Register Release
    rel_resp = client.post(f"/api/v1/projects/{proj_id}/releases", json={
        "version": "v1.0.0",
        "git_commit": "abcdef1234567890abcdef1234567890abcdef12",
        "image_tag": "v1.0.0",
        "commit_message": "Initial release"
    }, headers=admin_token_headers)
    assert rel_resp.status_code == 201
    rel_id = rel_resp.json()["data"]["id"]
    assert rel_resp.json()["data"]["version"] == "v1.0.0"

    # Trigger Vulnerability Scan
    scan_resp = client.post(f"/api/v1/projects/{proj_id}/releases/{rel_id}/scan", headers=admin_token_headers)
    assert scan_resp.status_code == 200
    scan_data = scan_resp.json()["data"]
    assert "critical_count" in scan_data
    assert scan_data["is_simulated"] is True
