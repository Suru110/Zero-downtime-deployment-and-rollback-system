def test_health_and_metrics_endpoints_are_exposed(client):
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"
    assert live.headers["X-Request-ID"]

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "releasepilot_http_requests_total" in metrics.text
    assert "releasepilot_http_request_duration_seconds" in metrics.text


def test_request_id_is_preserved(client):
    request_id = "observability-test-request"
    response = client.get("/livez", headers={"X-Request-ID": request_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
