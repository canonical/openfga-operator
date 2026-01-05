# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Callable

import jubilant
import yaml
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
CERTIFICATE_PROVIDER_APP = "ca"
CERTIFICATE_PROVIDER_CHARM = "self-signed-certificates"
DB_APP = "postgresql"
DB_CHARM = "postgresql-k8s"
OPENFGA_CLIENT_APP = "openfga-client"
OPENFGA_APP = "openfga"
TRAEFIK_CHARM = "traefik-k8s"
TRAEFIK_GRPC_APP = "traefik-grpc"
TRAEFIK_HTTP_APP = "traefik-http"
INGRESS_URL_REGEX = re.compile(r'"url":\s*"https?://(?P<netloc>[^/]+)')

logger = logging.getLogger(__name__)

StatusPredicate = Callable[[jubilant.Status], bool]


@contextmanager
def juju_model_factory(model_name: str, *, keep_model: bool = False) -> Iterator[jubilant.Juju]:
    juju = jubilant.Juju()
    try:
        juju.add_model(model_name, config={"logging-config": "<root>=INFO"})
    except jubilant.CLIError as e:
        if "already exists" not in e.stderr:
            raise

        juju.model = model_name

    try:
        yield juju
    finally:
        if not keep_model:
            with suppress(jubilant.CLIError):
                juju.destroy_model(model_name, destroy_storage=True, force=True)


def extract_certificate_common_name(certificate: str) -> str | None:
    cert_data = certificate.encode()
    cert = x509.load_pem_x509_certificate(cert_data, default_backend())
    if not (rdns := cert.subject.rdns):
        return None

    return rdns[0].rfc4514_string()


def get_unit_data(juju: jubilant.Juju, unit_name: str) -> dict:
    stdout = juju.cli("show-unit", unit_name)
    cmd_output = yaml.safe_load(stdout)
    return cmd_output[unit_name]


def get_integration_data(
    juju: jubilant.Juju, app_name: str, integration_name: str, unit_num: int = 0
) -> dict | None:
    data = get_unit_data(juju, f"{app_name}/{unit_num}")
    return next(
        (
            integration
            for integration in data["relation-info"]
            if integration["endpoint"] == integration_name
        ),
        None,
    )


def get_unit_address(juju: jubilant.Juju, app_name: str, unit_num: int = 0) -> str:
    data = get_unit_data(juju, f"{app_name}/{unit_num}")
    return data["address"]


def get_app_integration_data(
    juju: jubilant.Juju,
    app_name: str,
    integration_name: str,
    unit_num: int = 0,
) -> dict | None:
    data = get_integration_data(juju, app_name, integration_name, unit_num)
    return data["application-data"] if data else None


def get_unit_integration_data(
    juju: jubilant.Juju,
    app_name: str,
    remote_app_name: str,
    integration_name: str,
) -> dict | None:
    data = get_integration_data(juju, app_name, integration_name)
    return data["related-units"][f"{remote_app_name}/0"]["data"] if data else None


@contextmanager
def remove_integration(
    juju: jubilant.Juju, remote_app_name: str, integration_name: str
) -> Iterator[None]:
    juju.remove_relation(f"{OPENFGA_APP}:{integration_name}", remote_app_name)

    try:
        yield
    finally:
        try:
            for attempt in Retrying(
                retry=retry_if_exception_type(jubilant.CLIError),
                wait=wait_exponential(multiplier=2, min=1, max=30),
                stop=stop_after_attempt(10),
                reraise=True,
            ):
                with attempt:
                    juju.integrate(f"{OPENFGA_APP}:{integration_name}", remote_app_name)
        except RetryError:
            logger.error(
                "Failed to restore the integration: %s:%s - %s",
                OPENFGA_APP,
                integration_name,
                remote_app_name,
            )
            raise RuntimeError("Failed to restore integration")

        juju.wait(
            ready=lambda status: jubilant.all_active(status, OPENFGA_APP, remote_app_name),
            timeout=5 * 60,
        )


def all_active(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.all_active(status, *apps)


def all_blocked(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.all_blocked(status, *apps)


def any_error(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.any_error(status, *apps)


def is_active(app: str) -> StatusPredicate:
    return lambda status: status.apps[app].is_active


def is_blocked(app: str) -> StatusPredicate:
    return lambda status: status.apps[app].is_blocked


def unit_number(app: str, expected_num: int) -> StatusPredicate:
    return lambda status: len(status.apps[app].units) == expected_num


def and_(*predicates: StatusPredicate) -> StatusPredicate:
    return lambda status: all(predicate(status) for predicate in predicates)


def or_(*predicates: StatusPredicate) -> StatusPredicate:
    return lambda status: any(predicate(status) for predicate in predicates)
