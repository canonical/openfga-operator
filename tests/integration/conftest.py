# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import functools
import logging
import os
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Callable, Optional

import pytest
import pytest_asyncio
import yaml
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from juju.application import Application
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
CERTIFICATE_PROVIDER_APP = "self-signed-certificates"
DB_APP = "postgresql-k8s"
OPENFGA_CLIENT_APP = "openfga-client"
OPENFGA_APP = "openfga"
TRAEFIK_CHARM = "traefik-k8s"
TRAEFIK_GRPC_APP = "traefik-grpc"
TRAEFIK_HTTP_APP = "traefik-http"
INGRESS_URL_REGEX = re.compile(r'"url":\s*"https?://(?P<netloc>[^/]+)')


def extract_certificate_common_name(certificate: str) -> Optional[str]:
    cert_data = certificate.encode()
    cert = x509.load_pem_x509_certificate(cert_data, default_backend())
    if not (rdns := cert.subject.rdns):
        return None

    return rdns[0].rfc4514_string()


@pytest_asyncio.fixture(scope="module")
async def charm(ops_test: OpsTest) -> str | Path:
    if charm := os.getenv("CHARM_PATH"):
        return charm

    logger.info("Building OpenFGA charm locally")
    return await ops_test.build_charm(".")


@pytest_asyncio.fixture(scope="module")
async def tester_charm(ops_test: OpsTest) -> Path:
    if tester := next(Path("./tests/charms/openfga_requires").glob("*.charm"), None):
        return tester

    logger.info("Building OpenFGA tester charm locally")
    return await ops_test.build_charm("./tests/charms/openfga_requires/")


@pytest.fixture(scope="module", autouse=True)
def copy_libraries_into_tester_charm() -> None:
    src_lib_path = Path("lib/charms/openfga_k8s/v1/openfga.py")

    dest_dir = Path("tests/charms/openfga_requires") / src_lib_path.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_lib_path = dest_dir / src_lib_path.name

    shutil.copyfile(src_lib_path, dest_lib_path)


async def get_unit_data(ops_test: OpsTest, unit_name: str) -> dict:
    show_unit_cmd = f"show-unit {unit_name}".split()
    _, stdout, _ = await ops_test.juju(*show_unit_cmd)
    cmd_output = yaml.safe_load(stdout)
    return cmd_output[unit_name]


async def get_integration_data(
    ops_test: OpsTest, app_name: str, integration_name: str, unit_num: int = 0
) -> Optional[dict]:
    data = await get_unit_data(ops_test, f"{app_name}/{unit_num}")
    return next(
        (
            integration
            for integration in data["relation-info"]
            if integration["endpoint"] == integration_name
        ),
        None,
    )


async def get_app_integration_data(
    ops_test: OpsTest,
    app_name: str,
    integration_name: str,
    unit_num: int = 0,
) -> Optional[dict]:
    data = await get_integration_data(ops_test, app_name, integration_name, unit_num)
    return data["application-data"] if data else None


async def get_unit_integration_data(
    ops_test: OpsTest,
    app_name: str,
    remote_app_name: str,
    integration_name: str,
) -> Optional[dict]:
    data = await get_integration_data(ops_test, app_name, integration_name)
    return data["related-units"][f"{remote_app_name}/0"]["data"] if data else None


@pytest_asyncio.fixture
async def app_integration_data(ops_test: OpsTest) -> Callable:
    return functools.partial(get_app_integration_data, ops_test)


@pytest_asyncio.fixture
async def unit_integration_data(ops_test: OpsTest) -> Callable:
    return functools.partial(get_unit_integration_data, ops_test)


@pytest_asyncio.fixture
async def certificate_integration_data(app_integration_data: Callable) -> Optional[dict]:
    return await app_integration_data(OPENFGA_APP, "certificates")


@pytest_asyncio.fixture
async def openfga_integration_data(app_integration_data: Callable) -> Optional[dict]:
    return await app_integration_data(OPENFGA_CLIENT_APP, "openfga")


@pytest_asyncio.fixture
async def http_ingress_integration_data(app_integration_data: Callable) -> Optional[dict]:
    return await app_integration_data(OPENFGA_APP, "http-ingress")


@pytest_asyncio.fixture
async def grpc_ingress_integration_data(app_integration_data: Callable) -> Optional[dict]:
    return await app_integration_data(OPENFGA_APP, "grpc-ingress")


@pytest_asyncio.fixture
async def http_ingress_netloc(http_ingress_integration_data: Optional[dict]) -> Optional[str]:
    if not http_ingress_integration_data:
        return None

    ingress = http_ingress_integration_data["ingress"]
    matched = INGRESS_URL_REGEX.search(ingress)
    assert matched is not None, "ingress netloc not found in http ingress integration data"

    return matched.group("netloc")


@pytest_asyncio.fixture
async def grpc_ingress_netloc(grpc_ingress_integration_data: Optional[dict]) -> Optional[str]:
    if not grpc_ingress_integration_data:
        return None

    ingress = grpc_ingress_integration_data["ingress"]
    matched = INGRESS_URL_REGEX.search(ingress)
    assert matched is not None, "ingress netloc not found in grpc ingress integration data"

    return matched.group("netloc")


@pytest.fixture
def openfga_application(ops_test: OpsTest) -> Application:
    return ops_test.model.applications[OPENFGA_APP]


@pytest.fixture
def openfga_client_application(ops_test: OpsTest) -> Application:
    return ops_test.model.applications[OPENFGA_CLIENT_APP]


@asynccontextmanager
async def remove_integration(
    ops_test: OpsTest, remote_app_name: str, integration_name: str
) -> AsyncGenerator[None, None]:
    remove_integration_cmd = (
        f"remove-relation {OPENFGA_APP}:{integration_name} {remote_app_name}"
    ).split()
    await ops_test.juju(*remove_integration_cmd)
    await ops_test.model.wait_for_idle(
        apps=[remote_app_name],
        status="active",
    )

    try:
        yield
    finally:
        await ops_test.model.integrate(f"{OPENFGA_APP}:{integration_name}", remote_app_name)
        await ops_test.model.wait_for_idle(
            apps=[OPENFGA_APP, remote_app_name],
            status="active",
        )
