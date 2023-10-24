import logging
from pathlib import Path

import pytest_asyncio
from pytest_operator.plugin import OpsTest
from utils import fetch_charm

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture(scope="module")
async def charm(ops_test: OpsTest) -> Path:
    logger.info("Building local charm")
    charm = await fetch_charm(ops_test, "*.charm", ".")
    return charm


@pytest_asyncio.fixture(scope="module")
async def test_charm(ops_test: OpsTest) -> Path:
    logger.info("Building local test charm")
    test_charm = await fetch_charm(ops_test, "*.charm", "./tests/charms/openfga_requires/")
    return test_charm
