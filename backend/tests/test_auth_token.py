from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.deps import oauth2_scheme
from app.api.v1.auth import login, login_token
from app.core.security import decode_access_token
from app.schemas.auth import UserLogin
from app.main import app


def test_oauth2_form_token_authenticates_by_email(db_session, dev_user):
    response = login_token(
        SimpleNamespace(
            username=dev_user.email,
            password="DevPass123!",
        ),
        db_session,
    )

    claims = decode_access_token(response.access_token)
    assert response.token_type == "bearer"
    assert claims["sub"] == dev_user.id


def test_oauth2_form_token_rejects_invalid_credentials(db_session):
    with pytest.raises(HTTPException) as error:
        login_token(
            SimpleNamespace(
                username="unknown@example.com",
                password="wrong-password",
            ),
            db_session,
        )

    assert error.value.status_code == 401


def test_json_login_response_remains_unchanged(db_session, dev_user):
    response = login(
        UserLogin(email=dev_user.email, password="DevPass123!"),
        db_session,
    )

    assert response.success
    assert response.data.access_token
    assert response.data.user.id == dev_user.id


def test_swagger_oauth_flow_uses_form_token_endpoint():
    schema = app.openapi()
    security_scheme = schema["components"]["securitySchemes"][
        oauth2_scheme.scheme_name
    ]

    assert (
        security_scheme["flows"]["password"]["tokenUrl"]
        == "/api/v1/auth/token"
    )
