#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
from pathlib import Path
from typing import Callable, Optional

import pytest
from conftest import (
    CERTIFICATE_PROVIDER_APP,
    DB_APP,
    METADATA,
    OPENFGA_APP,
    OPENFGA_CLIENT_APP,
    TRAEFIK_CHARM,
    TRAEFIK_GRPC_APP,
    TRAEFIK_HTTP_APP,
    extract_certificate_common_name,
    remove_integration,
)
from juju.application import Application
from pytest_operator.plugin import OpsTest

from constants import CERTIFICATES_INTEGRATION_NAME, DATABASE_INTEGRATION_NAME

logger = logging.getLogger(__name__)


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, charm: Path, tester_charm: str) -> None:
    await asyncio.gather(
        ops_test.model.deploy(
            DB_APP,
            application_name=DB_APP,
            channel="14/stable",
            trust=True,
        ),
        ops_test.model.deploy(
            tester_charm,
            application_name=OPENFGA_CLIENT_APP,
            series="jammy",
            trust=True,
        ),
        ops_test.model.deploy(
            TRAEFIK_CHARM,
            application_name=TRAEFIK_GRPC_APP,
            channel="latest/stable",
            config={"external_hostname": "grpc_domain"},
            trust=True,
        ),
        ops_test.model.deploy(
            TRAEFIK_CHARM,
            application_name=TRAEFIK_HTTP_APP,
            channel="latest/stable",
            config={"external_hostname": "http_domain"},
            trust=True,
        ),
        ops_test.model.deploy(
            CERTIFICATE_PROVIDER_APP,
            channel="latest/stable",
            trust=True,
        ),
        ops_test.model.deploy(
            entity_url=str(charm),
            application_name=OPENFGA_APP,
            resources={"oci-image": METADATA["resources"]["oci-image"]["upstream-source"]},
            series="jammy",
            trust=True,
        ),
    )

    await ops_test.model.integrate(f"{OPENFGA_APP}:openfga", f"{OPENFGA_CLIENT_APP}:openfga")
    await ops_test.model.integrate(OPENFGA_APP, f"{DB_APP}:database")
    await ops_test.model.integrate(f"{OPENFGA_APP}:grpc-ingress", TRAEFIK_GRPC_APP)
    await ops_test.model.integrate(f"{OPENFGA_APP}:http-ingress", TRAEFIK_HTTP_APP)
    await ops_test.model.integrate(OPENFGA_APP, CERTIFICATE_PROVIDER_APP)
    await ops_test.model.wait_for_idle(
        apps=[
            CERTIFICATE_PROVIDER_APP,
            DB_APP,
            OPENFGA_APP,
            OPENFGA_CLIENT_APP,
            TRAEFIK_GRPC_APP,
            TRAEFIK_HTTP_APP,
        ],
        raise_on_error=False,
        status="active",
        timeout=10 * 60,
    )


async def test_openfga_integration(ops_test: OpsTest) -> None:
    openfga_requires_unit = ops_test.model.applications[OPENFGA_CLIENT_APP].units[0]
    assert "running with store" in openfga_requires_unit.workload_status_message


async def test_http_ingress_integration(http_ingress_netloc: Optional[str]) -> None:
    assert http_ingress_netloc, "HTTP ingress url not found in the http-ingress integration"
    assert http_ingress_netloc == "http_domain"


async def test_grpc_ingress_integration(grpc_ingress_netloc: Optional[str]) -> None:
    assert grpc_ingress_netloc, "GRPC ingress url not found in the grpc-ingress integration"
    assert grpc_ingress_netloc == "grpc_domain"


async def test_certification_integration(
    ops_test: OpsTest,
    certificate_integration_data: Optional[dict],
) -> None:
    assert certificate_integration_data
    certificates = json.loads(certificate_integration_data["certificates"])
    certificate = certificates[0]["certificate"]
    assert (
        f"CN={OPENFGA_APP}.{ops_test.model_name}.svc.cluster.local"
        == extract_certificate_common_name(certificate)
    )


async def test_certificate_transfer_integration(
    ops_test: OpsTest,
    unit_integration_data: Callable,
) -> None:
    await ops_test.model.integrate(
        f"{OPENFGA_CLIENT_APP}:receive-ca-cert",
        f"{OPENFGA_APP}:send-ca-cert",
    )

    await ops_test.model.wait_for_idle(
        apps=[OPENFGA_APP, OPENFGA_CLIENT_APP],
        status="active",
        timeout=5 * 60,
    )

    certificate_transfer_integration_data = await unit_integration_data(
        OPENFGA_CLIENT_APP,
        OPENFGA_APP,
        "receive-ca-cert",
    )
    assert certificate_transfer_integration_data, "Certificate transfer integration data is empty."

    for key in ("ca", "certificate", "chain"):
        assert key in certificate_transfer_integration_data, (
            f"Missing '{key}' in certificate transfer integration data."
        )

    chain = certificate_transfer_integration_data["chain"]
    assert isinstance(json.loads(chain), list), "Invalid certificate chain."

    certificate = certificate_transfer_integration_data["certificate"]
    assert (
        f"CN={OPENFGA_APP}.{ops_test.model_name}.svc.cluster.local"
        == extract_certificate_common_name(certificate)
    )


async def test_scale_up(ops_test: OpsTest) -> None:
    app = ops_test.model.applications[OPENFGA_APP]

    await app.scale(2)

    await ops_test.model.wait_for_idle(
        apps=[OPENFGA_APP],
        status="active",
        timeout=5 * 60,
        wait_for_exact_units=2,
    )
    await ops_test.model.wait_for_idle(
        apps=[OPENFGA_CLIENT_APP],
        status="active",
        timeout=5 * 60,
    )


async def test_remove_database_integration(
    ops_test: OpsTest, openfga_application: Application
) -> None:
    async with remove_integration(ops_test, DB_APP, DATABASE_INTEGRATION_NAME):
        assert openfga_application.status == "blocked"


async def test_remove_certificates_integration(
    ops_test: OpsTest,
    openfga_application: Application,
    openfga_client_application: Application,
) -> None:
    async with remove_integration(
        ops_test, CERTIFICATE_PROVIDER_APP, CERTIFICATES_INTEGRATION_NAME
    ):
        assert openfga_application.status == "active"
        assert openfga_client_application.status == "active"


async def test_scale_down(ops_test: OpsTest) -> None:
    app = ops_test.model.applications[OPENFGA_APP]

    await app.scale(1)

    await ops_test.model.wait_for_idle(
        apps=[OPENFGA_APP],
        status="active",
        timeout=10 * 60,
        wait_for_exact_units=1,
    )
    await ops_test.model.wait_for_idle(
        apps=[OPENFGA_CLIENT_APP],
        status="active",
        timeout=5 * 60,
    )
