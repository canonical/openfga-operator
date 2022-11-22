#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
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
    resources = {"openfga-image": METADATA["resources"]["openfga-image"]["upstream-source"]}

    # Deploy the charm and wait for active/idle status
    await asyncio.gather(
        ops_test.model.deploy(charm, resources=resources, application_name=APP_NAME, series='jammy'),
        ops_test.model.deploy("postgresql-k8s", application_name="postgresql"),
    )
    await ops_test.model.applications[APP_NAME].set_config({'dns-name': 'test-dns-name'})
    
    await ops_test.model.wait_for_idle(
        apps=["postgresql"], status="active", raise_on_blocked=True, timeout=1000
    )
    
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="blocked", timeout=1000
    )
    await ops_test.model.add_relation(APP_NAME, "postgresql:db")

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(apps=[APP_NAME])
    
    assert ops_test.model.applications[APP_NAME].status == "active"

