#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging

import pytest
import requests
from conftest import (
    DB_APP,
    METADATA,
    OPENFGA_APP,
    OPENFGA_CLIENT_APP,
    TRAEFIK_CHARM,
    TRAEFIK_GRPC_APP,
    TRAEFIK_HTTP_APP,
)
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


async def get_unit_address(ops_test: OpsTest, app_name: str, unit_num: int) -> str:
    """Get private address of a unit."""
    status = await ops_test.model.get_status()  # noqa: F821
    return status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["address"]


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, charm: str, test_charm: str) -> None:
    await asyncio.gather(
        ops_test.model.deploy(
            DB_APP,
            application_name=DB_APP,
            channel="14/stable",
            trust=True,
        ),
        ops_test.model.deploy(
            test_charm, application_name=OPENFGA_CLIENT_APP, series="jammy", trust=True
        ),
        ops_test.model.deploy(
            TRAEFIK_CHARM,
            application_name=TRAEFIK_GRPC_APP,
            channel="latest/stable",
            config={"external_hostname": "grpc"},
            trust=True,
        ),
        ops_test.model.deploy(
            TRAEFIK_CHARM,
            application_name=TRAEFIK_HTTP_APP,
            channel="latest/stable",
            config={"external_hostname": "http"},
            trust=True,
        ),
        ops_test.model.deploy(
            charm,
            application_name=OPENFGA_APP,
            resources={"oci-image": METADATA["resources"]["oci-image"]["upstream-source"]},
            series="jammy",
            trust=True,
        ),
    )

    await ops_test.model.integrate(OPENFGA_APP, f"{DB_APP}:database")
    await ops_test.model.integrate(f"{OPENFGA_APP}:grpc-ingress", TRAEFIK_GRPC_APP)
    await ops_test.model.integrate(f"{OPENFGA_APP}:http-ingress", TRAEFIK_HTTP_APP)
    await ops_test.model.wait_for_idle(
        apps=[
            DB_APP,
            OPENFGA_APP,
            TRAEFIK_GRPC_APP,
            TRAEFIK_HTTP_APP,
        ],
        status="active",
        timeout=10 * 60,
    )


async def test_requirer_charm_integration(ops_test: OpsTest) -> None:
    await ops_test.model.integrate(OPENFGA_APP, OPENFGA_CLIENT_APP)
    await ops_test.model.wait_for_idle(
        apps=[OPENFGA_CLIENT_APP, OPENFGA_APP],
        status="active",
        timeout=5 * 60,
    )

    openfga_requires_unit = ops_test.model.applications[OPENFGA_CLIENT_APP].units[0]
    assert "running with store" in openfga_requires_unit.workload_status_message


async def test_has_http_ingress(ops_test: OpsTest) -> None:
    http_address = await get_unit_address(ops_test, TRAEFIK_HTTP_APP, 0)

    resp = requests.get(f"http://{http_address}/{ops_test.model.name}-{OPENFGA_APP}/stores")

    assert resp.status_code == 401
    assert resp.json()["code"] == "bearer_token_missing"


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
