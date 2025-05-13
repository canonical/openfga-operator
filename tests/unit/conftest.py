# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import os
import pathlib
import tempfile
from typing import Generator
from unittest.mock import MagicMock, PropertyMock, create_autospec

import pytest
from ops import Container, Unit, testing
from ops.testing import ExecResult, Harness
from pytest_mock import MockerFixture

from charm import OpenFGAOperatorCharm


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


@pytest.fixture
def harness() -> Generator[Harness, None, None]:
    harness = Harness(OpenFGAOperatorCharm)
    harness.set_model_name("openfga-model")
    harness.add_oci_resource("oci-image")
    harness.set_can_connect("openfga", True)
    harness.set_leader(True)
    harness.begin()
    tempdir = tempfile.TemporaryDirectory()
    harness.charm.framework.charm_dir = pathlib.Path(tempdir.name)

    yield harness

    harness.cleanup()
    tempdir.cleanup()


@pytest.fixture
def mocked_migration_is_needed(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.OpenFGAOperatorCharm._migration_is_needed", return_value=False)


@pytest.fixture
def mocked_dsn(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charm.OpenFGAOperatorCharm._dsn",
        new_callable=PropertyMock,
        return_value="postgres://u:p@e/db",
    )


@pytest.fixture
def mocked_get_address(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.OpenFGAOperatorCharm._get_address", return_value="10.10.0.17")


@pytest.fixture
def mocked_create_openfga_store(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charm.OpenFGAOperatorCharm._create_openfga_store",
        return_value="01GK13VYZK62Q1T0X55Q2BHYD6",
    )


@pytest.fixture
def mocked_token_urlsafe(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("secrets.token_urlsafe", return_value="test-token")


@pytest.fixture
def mocked_juju_version(mocker: MockerFixture) -> MagicMock:
    return mocker.patch.dict(os.environ, {"JUJU_VERSION": "3.2.1"})


@pytest.fixture
def mocked_workload_version(harness: Harness) -> str:
    version = "1.0.0"
    harness.handle_exec(
        "openfga",
        ["openfga", "version"],
        result=ExecResult(
            stdout=b"",
            stderr=f"OpenFGA version `{version}` build from `abcd1234` on `2024-04-01 12:34:56`",
        ),
    )
    return version


@pytest.fixture(scope="module")
def provider_databag() -> dict:
    return {
        "store_id": "store_id",
        "token": "token",
        "token_secret_id": "token_secret_id",
        "grpc_api_url": "http://http/model-openfga",
        "http_api_url": "http://grpc/model-openfga",
    }


@pytest.fixture(scope="module")
def requirer_databag() -> dict:
    return {"store_name": "test-openfga-store"}
