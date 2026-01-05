# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import functools
import logging
import os
import secrets
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Callable

import jubilant
import pytest
import requests

from tests.integration.util import (
    INGRESS_URL_REGEX,
    OPENFGA_APP,
    OPENFGA_CLIENT_APP,
    get_app_integration_data,
    juju_model_factory,
)

logger = logging.getLogger(__name__)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--model",
        action="store",
        default=None,
        help="The model to run the tests on.",
    )
    parser.addoption(
        "--no-setup",
        action="store_true",
        default=False,
        help='Skip tests marked with "setup".',
    )
    parser.addoption(
        "--no-teardown",
        action="store_true",
        default=False,
        help='Skip tests marked with "teardown".',
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "setup: tests that setup some parts of the environment.")
    config.addinivalue_line(
        "markers", "teardown: tests that tear down some parts of the environment."
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_setup = pytest.mark.skip(reason="--no-setup provided.")
    skip_teardown = pytest.mark.skip(reason="--no-teardown provided.")

    for item in items:
        if config.getoption("--no-setup") and "setup" in item.keywords:
            item.add_marker(skip_setup)
        if config.getoption("--no-teardown") and "teardown" in item.keywords:
            item.add_marker(skip_teardown)
        if "upgrade" in item.nodeid.casefold():
            item.add_marker(pytest.mark.upgrade)


@pytest.fixture(scope="session")
def juju(request: pytest.FixtureRequest) -> Iterator[jubilant.Juju]:
    if not (model_name := request.config.getoption("--model")):
        model_name = f"test-openfga-{secrets.token_hex(4)}"

    no_teardown = bool(request.config.getoption("--no-teardown"))

    with juju_model_factory(model_name, keep_model=no_teardown) as juju:
        juju.wait_timeout = 10 * 60

        yield juju

        if request.session.testsfailed:
            log = juju.debug_log(limit=1000)
            print(log, end="")


@pytest.fixture(scope="session")
def openfga_charm() -> Path:
    if charm := os.getenv("CHARM_PATH"):
        return Path(charm)

    if local_charm := next(Path(".").glob("openfga-k8s*.charm"), None):
        return local_charm.resolve()

    logger.info("Building OpenFGA charm locally")
    try:
        subprocess.run(["charmcraft", "pack"], check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"OpenFGA charm build failed: {e}") from e

    if local_charm := next(Path(".").glob("openfga-k8s*.charm"), None):
        return Path(local_charm.resolve())
    else:
        raise FileNotFoundError("OpenFGA charm artifact not found")


@pytest.fixture
def openfga_tester_charm() -> Path:
    if tester := next(Path(".").glob("openfga-requires*.charm"), None):
        return tester.resolve()

    logger.info("Building OpenFGA tester charm locally")
    try:
        subprocess.run(
            ["charmcraft", "pack", "--project-dir", "tests/charms/openfga_requires"],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"OpenFGA tester charm build failed: {e}") from e

    if tester := next(Path(".").glob("openfga-requires*.charm"), None):
        return Path(tester.resolve())
    else:
        raise RuntimeError("OpenFGA tester charm artifact not found")


@pytest.fixture(scope="session", autouse=True)
def copy_libraries_into_tester_charm() -> None:
    src_lib_path = Path("lib/charms/openfga_k8s/v1/openfga.py")

    dest_dir = Path("tests/charms/openfga_requires") / src_lib_path.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_lib_path = dest_dir / src_lib_path.name

    shutil.copyfile(src_lib_path, dest_lib_path)


@pytest.fixture
def app_integration_data(juju: jubilant.Juju) -> Callable:
    return functools.partial(get_app_integration_data, juju)


@pytest.fixture
def openfga_integration_data(app_integration_data: Callable) -> dict | None:
    return app_integration_data(OPENFGA_CLIENT_APP, "openfga")


@pytest.fixture
def http_ingress_integration_data(app_integration_data: Callable) -> dict | None:
    return app_integration_data(OPENFGA_APP, "http-ingress")


@pytest.fixture
def grpc_ingress_integration_data(app_integration_data: Callable) -> dict | None:
    return app_integration_data(OPENFGA_APP, "grpc-ingress")


@pytest.fixture
def certificate_integration_data(app_integration_data: Callable) -> dict | None:
    return app_integration_data(OPENFGA_APP, "certificates")


@pytest.fixture
def http_ingress_netloc(http_ingress_integration_data: dict | None) -> str | None:
    if not http_ingress_integration_data:
        return None

    ingress = http_ingress_integration_data["ingress"]
    matched = INGRESS_URL_REGEX.search(ingress)
    assert matched is not None, "ingress netloc not found in http ingress integration data"

    return matched.group("netloc")


@pytest.fixture
def grpc_ingress_netloc(grpc_ingress_integration_data: dict | None) -> str | None:
    if not grpc_ingress_integration_data:
        return None

    ingress = grpc_ingress_integration_data["ingress"]
    matched = INGRESS_URL_REGEX.search(ingress)
    assert matched is not None, "ingress netloc not found in grpc ingress integration data"

    return matched.group("netloc")


@pytest.fixture
def http_client() -> Iterator[requests.Session]:
    with requests.Session() as client:
        client.verify = False
        yield client
