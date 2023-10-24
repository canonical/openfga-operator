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
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = "openfga"


@pytest.mark.abort_on_fail
async def test_upgrade_running_application(ops_test: OpsTest, charm, test_charm):
    """Deploy latest published charm and upgrade it with charm-under-test.

    Assert on the application status and health check endpoint after upgrade/refresh took place.
    """
    # Deploy the charm and wait for active/idle status
    logger.debug("deploying charms from store")
    await asyncio.gather(
        ops_test.model.deploy(
            METADATA["name"],
            application_name=APP_NAME,
            channel="edge",
            series="jammy",
        ),
        ops_test.model.deploy(
            "postgresql-k8s", application_name="postgresql", channel="edge", trust=True
        ),
        ops_test.model.deploy(
            test_charm,
            application_name="openfga-requires",
            series="jammy",
        ),
    )

    logger.debug("adding postgresql relation")
    await ops_test.model.wait_for_idle(
        apps=["postgresql"],
        status="active",
        timeout=1000,
    )
    openfga_unit = ops_test.model.applications[APP_NAME].units[0]
    await ops_test.model.block_until(
        lambda: (
            openfga_unit.workload_status in ["blocked"]
            and openfga_unit.workload_status_message == "Waiting for postgresql relation"
        ),
        timeout=60,
    )

    await ops_test.model.integrate(APP_NAME, "postgresql")
    await ops_test.model.block_until(
        lambda: (
            openfga_unit.workload_status in ["blocked"]
            and openfga_unit.workload_status_message == "Please run schema-upgrade action"
        ),
        timeout=60,
    )
    for i in range(10):
        action = await openfga_unit.run_action("schema-upgrade")
        result = await action.wait()
        logger.info("attempt {} -> action result {} {}".format(i, result.status, result.results))
        if result.results == {"result": "done", "return-code": 0}:
            break
        time.sleep(2)

    await ops_test.model.integrate(APP_NAME, "openfga-requires")
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=["openfga-requires"],
            status="active",
            timeout=60,
        )

    openfga_requires_unit = ops_test.model.applications["openfga-requires"].units[0]
    assert "running with store" in openfga_requires_unit.workload_status_message

    # Starting upgrade/refresh
    logger.debug("starting upgrade test")

    # Build and deploy charm from local source folder
    logger.debug("building local charm")

    resources = {"oci-image": METADATA["resources"]["oci-image"]["upstream-source"]}

    # Deploy the charm and wait for active/blocked status
    logger.debug("refreshing running application with the new local charm")

    await ops_test.model.applications[APP_NAME].refresh(
        path=charm,
        resources=resources,
    )
    await ops_test.model.block_until(
        lambda: ops_test.model.applications[APP_NAME].units[0].workload_status
        in ["blocked", "active"],
        timeout=60,
    )

    logger.debug("running schema-upgrade action")
    openfga_unit = ops_test.model.applications[APP_NAME].units[0]
    for i in range(10):
        action = await openfga_unit.run_action("schema-upgrade")
        result = await action.wait()
        logger.info("attempt {} -> action result {} {}".format(i, result.status, result.results))
        if result.results == {"result": "done", "return-code": 0}:
            break
        time.sleep(2)

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        timeout=60,
    )

    assert ops_test.model.applications[APP_NAME].status == "active"

    upgraded_openfga_unit = ops_test.model.applications[APP_NAME].units[0]

    health = await upgraded_openfga_unit.run("curl -s http://localhost:8080/healthz")
    await health.wait()
    assert health.results.get("return-code") == 0
    assert health.results.get("stdout").strip() == '{"status":"SERVING"}'
