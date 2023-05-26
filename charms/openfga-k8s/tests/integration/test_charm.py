#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd
# See LICENSE file for licensing details.

import asyncio
import logging
import time
from pathlib import Path

import pytest
import utils
import yaml
from juju.action import Action
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = "openfga"


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    # Build and deploy charm from local source folder
    charm = await ops_test.build_charm(".")
    resources = {"openfga-image": "localhost:32000/openfga:latest"}

    test_charm = await ops_test.build_charm("./tests/charms/openfga_requires/")

    # Deploy the charm and wait for active/idle status
    logger.debug("deploying charms")
    await asyncio.gather(
        ops_test.model.deploy(
            charm,
            resources=resources,
            application_name=APP_NAME,
            series="jammy",
        ),
        ops_test.model.deploy(
            "postgresql-k8s", application_name="postgresql", channel="edge"
        ),
        ops_test.model.deploy(
            test_charm,
            application_name="openfga-requires",
            series="jammy",
        ),
    )

    logger.debug("waiting for postgresql")
    await ops_test.model.wait_for_idle(
        apps=["postgresql", "openfga-requires"],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )

    logger.debug("adding postgresql relation")
    await ops_test.model.relate(APP_NAME, "postgresql:database")

    logger.debug("running schema-upgrade action")
    openfga_unit = await utils.get_unit_by_name(
        APP_NAME, "0", ops_test.model.units
    )
    for i in range(10):
        action: Action = await openfga_unit.run_action("schema-upgrade")
        result = await action.wait()
        logger.info(
            "attempt {} -> action result {} {}".format(
                i, result.status, result.results
            )
        )
        if result.results == {"result": "done", "return-code": 0}:
            break
        time.sleep(2)

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            status="active",
            timeout=60,
        )

    assert ops_test.model.applications[APP_NAME].status == "active"

    await ops_test.model.relate(APP_NAME, "openfga-requires")

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=["openfga-requires"],
            status="active",
            timeout=60,
        )

    openfga_requires_unit = await utils.get_unit_by_name(
        "openfga-requires", "0", ops_test.model.units
    )
    assert (
        "running with store" in openfga_requires_unit.workload_status_message
    )

@pytest.mark.abort_on_fail
async def test_upgrade_running_application(ops_test: OpsTest):
    """Deploy latest published charm and upgrade it with charm-under-test.

    Assert on the application status and health check endpoint after upgrade/refresh took place.
    """

    # Build charm that requires charm-under-test
    test_charm = await ops_test.build_charm("../openfga-requires/")

    # Deploy the charm and wait for active/idle status
    logger.debug("deploying charms from store")
    await asyncio.gather(
        ops_test.model.deploy(
            METADATA['name'],
            application_name=APP_NAME,
            channel="edge",
            series="jammy",
        ),
        ops_test.model.deploy(
            "postgresql-k8s", application_name="postgresql", channel="edge"
        ),
        ops_test.model.deploy(
            test_charm,
            application_name="openfga-requires",
            series="jammy",
        ),
    )

    logger.debug("waiting for postgresql")
    await ops_test.model.wait_for_idle(
        apps=["postgresql", "openfga-requires"],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )

    logger.debug("adding postgresql relation")
    await ops_test.model.relate(APP_NAME, "postgresql:database")

    logger.debug("running schema-upgrade action")
    openfga_unit = await utils.get_unit_by_name(
        APP_NAME, "0", ops_test.model.units
    )
    for i in range(10):
        action: Action = await openfga_unit.run_action("schema-upgrade")
        result = await action.wait()
        logger.info(
            "attempt {} -> action result {} {}".format(
                i, result.status, result.results
            )
        )
        if result.results == {"result": "done", "return-code": 0}:
            break
        time.sleep(2)

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            status="active",
            timeout=60,
        )

    assert ops_test.model.applications[APP_NAME].status == "active"

    await ops_test.model.relate(APP_NAME, "openfga-requires")

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=["openfga-requires"],
            status="active",
            timeout=60,
        )

    openfga_requires_unit = await utils.get_unit_by_name(
        "openfga-requires", "0", ops_test.model.units
    )
    assert (
        "running with store" in openfga_requires_unit.workload_status_message
    )

    # Starting upgrade/refresh
    logger.debug("starting upgrade test")

    # Build and deploy charm from local source folder
    logger.debug("building local charm")

    charm = await ops_test.build_charm(".")
    resources = {"openfga-image": "localhost:32000/openfga:latest"}

    # Deploy the charm and wait for active/idle status
    logger.debug("refreshing running application with the new local charm")

    await ops_test.model.applications[APP_NAME].refresh(
        path=charm,
        resources=resources,
    )

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            status="active",
            timeout=60,
        )

    assert ops_test.model.applications[APP_NAME].status == "active"

    upgraded_openfga_unit = await utils.get_unit_by_name(
        APP_NAME, "0", ops_test.model.units
    )

    health = await upgraded_openfga_unit.run("curl -s http://localhost:8080/healthz")
    await health.wait()
    assert health.results.get("return-code") == 0
    assert health.results.get("stdout").strip() == '{"status":"SERVING"}'
