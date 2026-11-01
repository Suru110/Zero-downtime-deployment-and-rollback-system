def test_register_and_login(client):
    register_payload = {
        "name": "New Developer",
        "email": "newdev@example.com",
        "password": "Password123!",
    }
    response = client.post("/api/v1/auth/register", json=register_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["data"]["name"] == "New Developer"
    assert data["data"]["role"] == "developer"
    assert "password_hash" not in data["data"]

    response = client.post("/api/v1/auth/login", json={
        "email": "newdev@example.com",
        "password": "Password123!",
    })
    assert response.status_code == 200
    token_data = response.json()["data"]
    assert "access_token" in token_data

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["email"] == "newdev@example.com"


def test_login_invalid_password(client, dev_user):
    response = client.post("/api/v1/auth/login", json={
        "email": dev_user.email,
        "password": "WrongPassword!",
    })
    assert response.status_code == 401


def test_registration_rejects_duplicate_email(client):
    payload = {
        "name": "New Developer",
        "email": "duplicate@example.com",
        "password": "Password123!",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409


def test_registration_rejects_weak_password(client):
    response = client.post("/api/v1/auth/register", json={
        "name": "New Developer",
        "email": "weak@example.com",
        "password": "password",
    })
    assert response.status_code == 422
