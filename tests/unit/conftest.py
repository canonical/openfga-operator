# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import os
import pathlib
import tempfile
from typing import Generator
from unittest.mock import MagicMock, PropertyMock

import pytest
from ops.testing import ExecResult, Harness
from pytest_mock import MockerFixture

from charm import OpenFGAOperatorCharm


@pytest.fixture
def harness(mocked_kubernetes_service_patcher: MagicMock) -> Generator[Harness, None, None]:
    harness = Harness(OpenFGAOperatorCharm)
    harness.set_model_name("openfga-model")
    harness.add_oci_resource("oci-image")
    harness.set_leader(True)
    harness.begin()
    tempdir = tempfile.TemporaryDirectory()
    harness.charm.framework.charm_dir = pathlib.Path(tempdir.name)

    yield harness

    harness.cleanup()
    tempdir.cleanup()


@pytest.fixture
def mocked_kubernetes_service_patcher(mocker: MockerFixture) -> MagicMock:
    mocked_service_patcher = mocker.patch("charm.KubernetesServicePatch")
    mocked_service_patcher.return_value = lambda x, y: None
    return mocked_service_patcher


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
