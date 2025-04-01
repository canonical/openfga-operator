# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import functools
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Callable, Optional

import pytest
import pytest_asyncio
import yaml
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from pytest_operator.plugin import OpsTest
from utils import fetch_charm

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
async def charm(ops_test: OpsTest) -> Path:
    # in GitHub CI, charms are built with charmcraftcache and uploaded to $CHARM_PATH
    charm = os.getenv("CHARM_PATH")
    if not charm:
        # fall back to build locally - required when run outside of GitHub CI
        charm = await ops_test.build_charm(".")
    return charm


@pytest_asyncio.fixture(scope="module")
async def test_charm(ops_test: OpsTest) -> Path:
    logger.info("Building local test charm")
    test_charm = await fetch_charm(ops_test, "*.charm", "./tests/charms/openfga_requires/")
    return test_charm


@pytest.fixture(scope="module", autouse=True)
def copy_libraries_into_tester_charm() -> None:
    """Ensure that the tester charm uses the current libraries."""
    lib = Path("lib/charms/openfga_k8s/v1/openfga.py")
    Path("tests/integration/openfga_requires", lib.parent).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(lib.as_posix(), "tests/charms/openfga_requires/{}".format(lib.as_posix()))


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
