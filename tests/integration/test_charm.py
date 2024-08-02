#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import requests
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
OPENFGA_APP = "openfga"
TRAEFIK_CHARM = "traefik-k8s"
TRAEFIK_GRPC_APP = "traefik-grpc"
TRAEFIK_HTTP_APP = "traefik-http"


async def get_unit_address(ops_test: OpsTest, app_name: str, unit_num: int) -> str:
    """Get private address of a unit."""
    status = await ops_test.model.get_status()  # noqa: F821
    return status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["address"]


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, charm: str, test_charm: str) -> None:
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    resources = {"oci-image": METADATA["resources"]["oci-image"]["upstream-source"]}
    # Deploy the charm and wait for active/idle status
    logger.debug("deploying charms")
    await asyncio.gather(
        ops_test.model.deploy(
            charm, resources=resources, application_name=OPENFGA_APP, series="jammy", trust=True
        ),
        ops_test.model.deploy(
            "postgresql-k8s", application_name="postgresql", channel="edge", trust=True
        ),
        ops_test.model.deploy(
            test_charm,
            application_name="openfga-requires",
            series="jammy",
            num_units=2,
        ),
    )

    logger.debug("adding postgresql relation")
    await ops_test.model.integrate(OPENFGA_APP, "postgresql:database")
    await ops_test.model.wait_for_idle(
        apps=[OPENFGA_APP, "postgresql"],
        status="active",
        timeout=1000,
    )

    await ops_test.model.deploy(
        TRAEFIK_CHARM,
        application_name=TRAEFIK_GRPC_APP,
        channel="latest/edge",
        config={"external_hostname": "grpc"},
    )
    await ops_test.model.deploy(
        TRAEFIK_CHARM,
        application_name=TRAEFIK_HTTP_APP,
        channel="latest/edge",
        config={"external_hostname": "http"},
    )
    await ops_test.model.wait_for_idle(
        apps=[TRAEFIK_GRPC_APP, TRAEFIK_HTTP_APP],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )

    await ops_test.model.integrate(f"{OPENFGA_APP}:grpc-ingress", TRAEFIK_GRPC_APP)
    await ops_test.model.integrate(f"{OPENFGA_APP}:http-ingress", TRAEFIK_HTTP_APP)


async def test_requirer_charm_integration(ops_test: OpsTest) -> None:
    assert ops_test.model.applications[OPENFGA_APP].status == "active"

    await ops_test.model.integrate(OPENFGA_APP, "openfga-requires")
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=["openfga-requires"],
            status="active",
            timeout=60,
        )

    openfga_requires_unit = ops_test.model.applications["openfga-requires"].units[0]
    assert "running with store" in openfga_requires_unit.workload_status_message


async def test_has_http_ingress(ops_test: OpsTest) -> None:
    # Get the traefik address and try to reach openfga
    http_address = await get_unit_address(ops_test, TRAEFIK_HTTP_APP, 0)

    resp = requests.get(f"http://{http_address}/{ops_test.model.name}-{OPENFGA_APP}/stores")

    assert resp.status_code == 401
    assert resp.json()["code"] == "bearer_token_missing"


async def test_scale_up(ops_test: OpsTest) -> None:
    """Check that openfga works after it is scaled up."""
    app = ops_test.model.applications[OPENFGA_APP]

    await app.scale(3)

    await ops_test.model.wait_for_idle(
        apps=[OPENFGA_APP],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
        wait_for_exact_units=3,
    )


async def test_scale_down(ops_test: OpsTest) -> None:
    """Check that openfga works after it is scaled up."""
    app = ops_test.model.applications[OPENFGA_APP]

    await app.scale(3)

    await ops_test.model.wait_for_idle(
        apps=[OPENFGA_APP],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
        wait_for_exact_units=3,
    )
