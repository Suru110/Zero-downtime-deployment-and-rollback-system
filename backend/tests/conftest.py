import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Force SQLite in-memory for testing
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ENABLE_MOCK_ADAPTERS"] = "true"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-1234567890"

from app.core.database import Base
import app.models  # ensure models are loaded
from app.api.deps import get_db
from app.main import app
from app.core.security import get_password_hash, create_access_token
from app.models.user import User

TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def admin_user(db_session):
    user = User(
        username="admin_tester",
        email="admin_tester@test.local",
        hashed_password=get_password_hash("AdminPass123!"),
        role="admin"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

@pytest.fixture
def admin_token_headers(admin_user):
    token = create_access_token(subject=admin_user.id, role=admin_user.role)
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def dev_user(db_session):
    user = User(
        username="dev_tester",
        email="dev_tester@example.com",
        hashed_password=get_password_hash("DevPass123!"),
        role="developer"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

@pytest.fixture
def dev_token_headers(dev_user):
    token = create_access_token(subject=dev_user.id, role=dev_user.role)
    return {"Authorization": f"Bearer {token}"}
