import pytest
import uuid

from app.models.deployment import Deployment
from app.models.environment import Environment
from app.models.project import Project
from app.models.release import Release
from app.adapters.base import AdapterResult
from app.services.deployment_engine import DeploymentEngine
from app.services.public_endpoint import is_public_http_url


def run_immediate(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError("The route attempted asynchronous I/O in this unit test.")


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://sample.trycloudflare.com", True),
        ("https://example.com/app", True),
        ("http://127.0.0.1:3000", False),
        ("http://localhost:3000", False),
        ("http://10.2.3.4", False),
        ("http://169.254.10.2", False),
        ("http://service.namespace.svc.cluster.local", False),
        ("", False),
        ("not a url", False),
    ],
)
def test_is_public_http_url(url, expected):
    assert is_public_http_url(url) is expected


def create_deployment(db_session, user_id, metadata_info=None):
    project = Project(
        name=f"endpoint-test-{uuid.uuid4().hex[:8]}",
        git_repo="https://example.com/source.git",
        image_repository="example/endpoint-test",
        default_port=3000,
        health_path="/healthz",
        owner_id=user_id,
    )
    db_session.add(project)
    db_session.flush()

    environment = Environment(
        project_id=project.id,
        name="staging",
        k8s_namespace="endpoint-test-staging",
    )
    release = Release(
        project_id=project.id,
        version="v1",
        git_commit="1234567890abcdef1234567890abcdef12345678",
        image_tag="v1",
    )
    db_session.add_all([environment, release])
    db_session.flush()

    deployment = Deployment(
        project_id=project.id,
        environment_id=environment.id,
        release_id=release.id,
        status="active",
        metadata_info=metadata_info or {},
    )
    db_session.add(deployment)
    db_session.commit()
    db_session.refresh(deployment)
    return deployment


def test_endpoint_metadata_persists_and_all_deployment_apis_agree(
    db_session,
    admin_user,
    monkeypatch,
):
    from app.api.v1 import deployments as deployment_routes

    deployment = create_deployment(db_session, admin_user.id)
    endpoint_details = {
        "status": "ready",
        "local_url": "http://127.0.0.1:41000",
        "service_name": "endpoint-test-project",
        "namespace": "endpoint-test-staging",
        "service_port": 3000,
        "tunnel_provider": "cloudflare-quick-tunnel",
        "tunnel_process_state": "running",
        "last_verified_at": "2026-11-13T00:00:00+00:00",
    }

    class EndpointAdapter:
        async def discover_service_endpoint(self, **kwargs):
            assert kwargs["deployment_id"] == deployment.id
            assert kwargs["namespace"] == "endpoint-test-staging"
            return {
                **endpoint_details,
                "public_url": "https://dynamic-name.trycloudflare.com",
            }

    def get_adapter(mode=None):
        assert mode == "production"
        return EndpointAdapter()

    monkeypatch.setattr(deployment_routes, "get_deployment_adapter", get_adapter)
    monkeypatch.setattr(
        deployment_routes.cloudflare_tunnel_service,
        "has_running_tunnel",
        lambda deployment_id, public_url: True,
    )

    endpoint_response = run_immediate(
        deployment_routes.get_deployment_endpoint(
            deployment.id,
            db_session,
            admin_user,
        )
    )
    assert endpoint_response.success
    endpoint_data = endpoint_response.data.model_dump()
    expected_url = "https://dynamic-name.trycloudflare.com"
    assert endpoint_data["metadata_info"]["endpoint_status"] == "ready"
    assert endpoint_data["metadata_info"]["public_url"] == expected_url
    assert endpoint_data["metadata_info"]["endpoint_details"] == endpoint_details
    assert "public_url" not in endpoint_data["metadata_info"]["adapter_details"]

    detail_response = deployment_routes.get_deployment(
        deployment.id,
        db_session,
        admin_user,
    )
    list_response = deployment_routes.list_deployments(
        None,
        None,
        50,
        0,
        db_session,
        admin_user,
    )
    detail_metadata = detail_response.data.model_dump()["metadata_info"]
    list_metadata = next(
        item.model_dump()["metadata_info"]
        for item in list_response.data
        if item.id == deployment.id
    )
    assert detail_metadata == endpoint_data["metadata_info"]
    assert list_metadata == endpoint_data["metadata_info"]

    db_session.expire_all()
    persisted = db_session.query(Deployment).filter_by(id=deployment.id).one()
    assert persisted.metadata_info["public_url"] == expected_url
    assert persisted.metadata_info["endpoint_details"]["tunnel_process_state"] == "running"


def test_invalid_ready_endpoint_is_saved_as_pending_without_old_url(
    db_session,
    admin_user,
    monkeypatch,
):
    from app.api.v1 import deployments as deployment_routes

    deployment = create_deployment(
        db_session,
        admin_user.id,
        {
            "public_url": "http://127.0.0.1:3000",
            "endpoint_status": "ready",
            "adapter_details": {"public_url": "http://127.0.0.1:3000"},
        },
    )

    class LocalEndpointAdapter:
        async def discover_service_endpoint(self, **kwargs):
            return {
                "status": "ready",
                "public_url": "http://127.0.0.1:3000",
            }

    def get_adapter(mode=None):
        assert mode == "production"
        return LocalEndpointAdapter()

    monkeypatch.setattr(deployment_routes, "get_deployment_adapter", get_adapter)

    response = run_immediate(
        deployment_routes.get_deployment_endpoint(
            deployment.id,
            db_session,
            admin_user,
        )
    )
    metadata = response.data.model_dump()["metadata_info"]

    assert response.success
    assert metadata["endpoint_status"] == "pending"
    assert "public_url" not in metadata
    assert "public_url" not in metadata["adapter_details"]
    assert metadata["endpoint_details"]["status"] == "pending"


def test_simulated_deployment_endpoint_recovery_uses_mock_adapter(
    db_session,
    admin_user,
    monkeypatch,
):
    from app.api.v1 import deployments as deployment_routes

    deployment = create_deployment(db_session, admin_user.id)
    deployment.is_simulated = True

    class MockEndpointAdapter:
        async def discover_service_endpoint(self, **kwargs):
            return {
                "status": "unavailable",
                "error": "The simulated adapter does not provide a public endpoint.",
            }

    def get_adapter(mode=None):
        assert mode == "mock"
        return MockEndpointAdapter()

    monkeypatch.setattr(deployment_routes, "get_deployment_adapter", get_adapter)

    response = run_immediate(
        deployment_routes.get_deployment_endpoint(
            deployment.id,
            db_session,
            admin_user,
        )
    )
    metadata = response.data.model_dump()["metadata_info"]

    assert metadata["endpoint_status"] == "unavailable"
    assert metadata["endpoint_error"] == (
        "The simulated adapter does not provide a public endpoint."
    )
    assert "public_url" not in metadata


def test_deployment_read_invalidates_stopped_quick_tunnel(
    db_session,
    admin_user,
    monkeypatch,
):
    from app.api.v1 import deployments as deployment_routes

    url = "https://expired.trycloudflare.com"
    deployment = create_deployment(
        db_session,
        admin_user.id,
        {
            "public_url": url,
            "endpoint_status": "ready",
            "endpoint_details": {
                "status": "ready",
                "tunnel_provider": "cloudflare-quick-tunnel",
                "tunnel_process_state": "running",
            },
            "adapter_details": {"public_url": url},
        },
    )
    monkeypatch.setattr(
        deployment_routes.cloudflare_tunnel_service,
        "has_running_tunnel",
        lambda deployment_id, public_url: False,
    )

    response = deployment_routes.get_deployment(
        deployment.id,
        db_session,
        admin_user,
    )
    metadata = response.data.model_dump()["metadata_info"]

    assert response.success
    assert metadata["endpoint_status"] == "pending"
    assert metadata["endpoint_details"]["tunnel_process_state"] == "stopped"
    assert "public_url" not in metadata
    assert "public_url" not in metadata["adapter_details"]


def test_backend_restart_invalidates_persisted_quick_tunnel(
    db_session,
    admin_user,
    monkeypatch,
):
    from app import main

    url = "https://restart-stale.trycloudflare.com"
    deployment = create_deployment(
        db_session,
        admin_user.id,
        {
            "public_url": url,
            "endpoint_status": "ready",
            "adapter_details": {"public_url": url},
            "endpoint_details": {
                "status": "ready",
                "local_url": "http://127.0.0.1:41234",
                "namespace": "endpoint-test-staging",
                "service_name": "endpoint-test-project",
                "tunnel_provider": "cloudflare-quick-tunnel",
                "tunnel_process_state": "running",
                "process_ids": {"cloudflared": 1234, "port_forward": 5678},
            },
        },
    )
    db_stub = type(
        "DatabaseStub",
        (),
        {
            "__enter__": lambda self: self,
            "__exit__": lambda self, *args: False,
            "query": lambda self, _model: type(
                "QueryStub", (), {"all": lambda self: [deployment]}
            )(),
            "commit": lambda self: None,
        },
    )()
    monkeypatch.setattr(main, "SessionLocal", lambda: db_stub)
    cleanup_calls = []
    monkeypatch.setattr(
        main.cloudflare_tunnel_service,
        "cleanup_orphaned_processes",
        lambda processes: cleanup_calls.extend(processes) or len(processes),
    )

    main._reset_stale_quick_tunnels()

    metadata = deployment.metadata_info
    assert metadata["endpoint_status"] == "pending"
    assert "Backend restarted" in metadata["endpoint_error"]
    assert "public_url" not in metadata
    assert "public_url" not in metadata["adapter_details"]
    assert metadata["endpoint_details"]["status"] == "pending"
    assert metadata["endpoint_details"]["tunnel_process_state"] == "stopped"
    assert "process_ids" not in metadata["endpoint_details"]
    assert len(cleanup_calls) == 2


@pytest.mark.asyncio
async def test_real_deployment_fails_without_verified_public_endpoint(
    db_session,
    admin_user,
    monkeypatch,
):
    from app.services import deployment_engine

    deployment = create_deployment(db_session, admin_user.id)
    deployment.status = "pending"
    environment = db_session.query(Environment).filter_by(
        id=deployment.environment_id
    ).one()
    environment.auto_rollback_enabled = False
    release = db_session.query(Release).filter_by(id=deployment.release_id).one()
    release.image_reference = "example/endpoint-test:v1"
    db_session.commit()

    class ProductionAdapter:
        adapter_name = "k8s-production-adapter"
        is_simulated = False

        async def deploy(self, **kwargs):
            return AdapterResult(
                success=True,
                is_simulated=False,
                adapter_name=self.adapter_name,
                message="Kubernetes rollout completed.",
                details={
                    "endpoint_status": "pending",
                    "endpoint_error": "No ready public service endpoint.",
                },
            )

    monkeypatch.setattr(
        deployment_engine,
        "get_deployment_adapter",
        lambda: ProductionAdapter(),
    )

    await DeploymentEngine.execute_deployment(
        db_session,
        deployment.id,
    )

    assert deployment.status == "failed"
    assert deployment.metadata_info["endpoint_status"] == "error"
    assert "public service endpoint" in deployment.metadata_info["endpoint_error"]
    assert deployment.metadata_info["namespace"] == environment.k8s_namespace


@pytest.mark.asyncio
async def test_real_deployment_becomes_active_only_after_public_url_verification(
    db_session,
    admin_user,
    monkeypatch,
):
    from app.services import deployment_engine

    deployment = create_deployment(db_session, admin_user.id)
    deployment.status = "pending"
    environment = db_session.query(Environment).filter_by(
        id=deployment.environment_id
    ).one()
    environment.auto_rollback_enabled = False
    release = db_session.query(Release).filter_by(id=deployment.release_id).one()
    release.image_reference = "example/endpoint-test:v1"
    db_session.commit()
    verified_at = "2026-11-13T00:00:00+00:00"
    public_url = "https://verified-endpoint.trycloudflare.com"

    class ProductionAdapter:
        adapter_name = "k8s-production-adapter"
        is_simulated = False

        async def deploy(self, **kwargs):
            return AdapterResult(
                success=True,
                is_simulated=False,
                adapter_name=self.adapter_name,
                message="Kubernetes rollout and public endpoint were verified.",
                details={
                    "endpoint_status": "ready",
                    "public_url": public_url,
                    "endpoint_details": {
                        "status": "ready",
                        "namespace": environment.k8s_namespace,
                        "service_name": "endpoint-test-service",
                        "service_type": "NodePort",
                        "service_port": 3000,
                        "target_port": "http",
                        "resolved_target_port": 3000,
                        "endpoint_provider": "cloudflare-quick-tunnel",
                        "last_verified_at": verified_at,
                    },
                },
            )

    async def verify_deployment(**kwargs):
        return True

    monkeypatch.setattr(
        deployment_engine,
        "get_deployment_adapter",
        lambda: ProductionAdapter(),
    )
    monkeypatch.setattr(
        deployment_engine.HealthMonitorService,
        "verify_deployment",
        verify_deployment,
    )

    await DeploymentEngine.execute_deployment(
        db_session,
        deployment.id,
    )

    assert deployment.status == "active"
    assert deployment.metadata_info["public_url"] == public_url
    assert deployment.metadata_info["endpoint_status"] == "ready"
    assert deployment.metadata_info["namespace"] == environment.k8s_namespace
    assert deployment.metadata_info["service_name"] == "endpoint-test-service"
    assert deployment.metadata_info["service_port"] == 3000
    assert deployment.metadata_info["target_port"] == "http"
    assert deployment.metadata_info["last_verified_at"] == verified_at
