import logging
import shutil
from pathlib import Path

import pytest
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


@pytest.fixture(scope="module", autouse=True)
def copy_libraries_into_tester_charm(ops_test: OpsTest) -> None:
    """Ensure that the tester charm uses the current libraries."""
    lib = Path("lib/charms/openfga_k8s/v0/openfga.py")
    Path("tests/integration/openfga_requires", lib.parent).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(lib.as_posix(), "tests/charms/openfga_requires/{}".format(lib.as_posix()))
