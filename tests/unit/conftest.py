# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, PropertyMock, create_autospec

import pytest
from ops import Container, Unit, testing
from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def mocked_k8s_resource_patch(mocker: MockerFixture) -> None:
    mocker.patch(
        "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher",
        autospec=True,
    )
    mocker.patch.multiple(
        "charm.KubernetesComputeResourcesPatch",
        _namespace="testing",
        _patch=lambda *a, **kw: None,
        is_ready=lambda *a, **kw: True,
    )


@pytest.fixture
def mocked_container() -> MagicMock:
    return create_autospec(Container)


@pytest.fixture
def mocked_unit(mocked_container: MagicMock) -> MagicMock:
    mocked = create_autospec(Unit)
    mocked.get_container.return_value = mocked_container
    return mocked


@pytest.fixture
def mocked_workload_service(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.WorkloadService", autospec=True)


@pytest.fixture
def mocked_workload_service_version(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charm.WorkloadService.version", new_callable=PropertyMock, return_value="1.0.0"
    )


@pytest.fixture
def mocked_workload_service_running(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charm.WorkloadService.is_running", new_callable=PropertyMock, return_value=True
    )


@pytest.fixture
def mocked_database_resource_created(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.DatabaseRequires.is_resource_created", return_value=True)


@pytest.fixture
def mocked_charm_holistic_handler(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.OpenFGAOperatorCharm._holistic_handler")


@pytest.fixture
def mocked_migration_needed(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charm.OpenFGAOperatorCharm.migration_needed", new_callable=PropertyMock, return_value=True
    )


@pytest.fixture
def peer_integration() -> testing.Relation:
    return testing.PeerRelation(
        endpoint="peer",
        interface="openfga-peer",
    )


@pytest.fixture
def database_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="database",
        interface="postgresql_client",
        remote_app_name="postgresql-k8s",
        remote_app_data={
            "data": '{"database": "openfga", "extra-user-roles": "SUPERUSER"}',
            "database": "database",
            "endpoints": "endpoints",
            "username": "username",
            "password": "password",
        },
    )


@pytest.fixture
def http_ingress_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="http-ingress",
        interface="ingress",
        remote_app_name="traefik-http",
        remote_app_data={"ingress": '{"url": "https://http.test.com"}'},
    )


@pytest.fixture
def grpc_ingress_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="grpc-ingress",
        interface="ingress",
        remote_app_name="traefik-grpc",
        remote_app_data={"ingress": '{"url": "https://grpc.test.com"}'},
    )


@pytest.fixture
def openfga_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="openfga",
        interface="openfga",
        remote_app_name="openfga-client",
        remote_app_data={
            "store_name": "test-openfga-store",
        },
    )


@pytest.fixture
def certificates_transfer_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="send-ca-cert",
        interface="certificate_transfer",
        remote_app_name="openfga-client",
    )


@pytest.fixture
def tracing_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="tracing",
        interface="tracing",
        remote_app_name="tempo-coordinator-k8s",
    )
