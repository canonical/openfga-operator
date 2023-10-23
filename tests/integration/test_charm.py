#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import utils
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = "openfga"


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, charm, test_charm):
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    resources = {"oci-image": METADATA["resources"]["oci-image"]["upstream-source"]}
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
            "postgresql-k8s", application_name="postgresql", channel="edge", trust=True
        ),
        ops_test.model.deploy(
            test_charm,
            application_name="openfga-requires",
            series="jammy",
        ),
    )

    logger.debug("waiting for postgresql")
    await ops_test.model.wait_for_idle(
        apps=["postgresql"],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )

    logger.debug("adding postgresql relation")
    await ops_test.model.integrate(APP_NAME, "postgresql:database")
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        timeout=60,
    )

    assert ops_test.model.applications[APP_NAME].status == "active"

    await ops_test.model.integrate(APP_NAME, "openfga-requires")

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=["openfga-requires"],
            status="active",
            timeout=60,
        )

    openfga_requires_unit = await utils.get_unit_by_name(
        "openfga-requires", "0", ops_test.model.units
    )
    assert "running with store" in openfga_requires_unit.workload_status_message
