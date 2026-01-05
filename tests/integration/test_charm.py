# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from pathlib import Path

import jubilant
import pytest

from tests.integration.util import (
    CERTIFICATE_PROVIDER_APP,
    CERTIFICATE_PROVIDER_CHARM,
    DB_APP,
    DB_CHARM,
    METADATA,
    OPENFGA_APP,
    OPENFGA_CLIENT_APP,
    TRAEFIK_CHARM,
    TRAEFIK_GRPC_APP,
    TRAEFIK_HTTP_APP,
    all_active,
    all_blocked,
    and_,
    any_error,
    extract_certificate_common_name,
    get_app_integration_data,
    remove_integration,
    unit_number,
)

logger = logging.getLogger(__name__)


@pytest.mark.setup
def test_build_and_deploy(
    juju: jubilant.Juju, openfga_charm: Path, openfga_tester_charm: Path
) -> None:
    juju.deploy(
        charm=DB_CHARM,
        app=DB_APP,
        channel="14/stable",
        trust=True,
    )

    juju.deploy(
        charm=openfga_tester_charm,
        app=OPENFGA_CLIENT_APP,
        trust=True,
    )

    juju.deploy(
        charm=TRAEFIK_CHARM,
        app=TRAEFIK_GRPC_APP,
        channel="latest/stable",
        config={"external_hostname": "grpc_domain"},
        trust=True,
    )

    juju.deploy(
        charm=TRAEFIK_CHARM,
        app=TRAEFIK_HTTP_APP,
        channel="latest/stable",
        config={"external_hostname": "http_domain"},
        trust=True,
    )

    juju.deploy(
        charm=CERTIFICATE_PROVIDER_CHARM,
        app=CERTIFICATE_PROVIDER_APP,
        channel="latest/stable",
        trust=True,
    )

    juju.deploy(
        charm=openfga_charm,
        app=OPENFGA_APP,
        resources={"oci-image": METADATA["resources"]["oci-image"]["upstream-source"]},
        trust=True,
    )

    juju.integrate(f"{OPENFGA_APP}:openfga", f"{OPENFGA_CLIENT_APP}:openfga")
    juju.integrate(OPENFGA_APP, f"{DB_APP}:database")
    juju.integrate(f"{OPENFGA_APP}:grpc-ingress", TRAEFIK_GRPC_APP)
    juju.integrate(f"{OPENFGA_APP}:http-ingress", TRAEFIK_HTTP_APP)
    juju.integrate(OPENFGA_APP, CERTIFICATE_PROVIDER_APP)

    juju.wait(
        ready=all_active(
            DB_APP,
            OPENFGA_APP,
            OPENFGA_CLIENT_APP,
            CERTIFICATE_PROVIDER_APP,
        ),
        error=any_error(
            DB_APP,
            OPENFGA_APP,
            OPENFGA_CLIENT_APP,
            CERTIFICATE_PROVIDER_APP,
        ),
        timeout=10 * 60,
    )


def test_database_integration(juju: jubilant.Juju) -> None:
    database_integration_data = get_app_integration_data(
        juju, app_name=OPENFGA_APP, integration_name="database"
    )
    assert database_integration_data, "Database integration data is empty."
    assert database_integration_data["endpoints"]
    assert "read-only-endpoints" not in database_integration_data, (
        "Read-only endpoints should be empty."
    )

    # Scale up the database
    juju.cli("scale-application", DB_APP, "2")

    juju.wait(
        ready=all_active(DB_APP, OPENFGA_APP),
        timeout=10 * 60,
    )

    database_integration_data = get_app_integration_data(
        juju, app_name=OPENFGA_APP, integration_name="database"
    )
    assert database_integration_data, "Database integration data is empty."
    assert database_integration_data["endpoints"]
    assert database_integration_data["read-only-endpoints"], "Read-only endpoints missing."


def test_openfga_integration(openfga_integration_data: dict | None) -> None:
    assert openfga_integration_data, "Openfga integration data is empty."
    assert openfga_integration_data["store_id"]
    assert openfga_integration_data["grpc_api_url"]
    assert openfga_integration_data["http_api_url"]
    assert openfga_integration_data["token_secret_id"]


def test_http_ingress_integration(http_ingress_netloc: str | None) -> None:
    assert http_ingress_netloc, "HTTP ingress url not found in the http-ingress integration"
    assert http_ingress_netloc == "http_domain"


def test_grpc_ingress_integration(grpc_ingress_netloc: str | None) -> None:
    assert grpc_ingress_netloc, "GRPC ingress url not found in the grpc-ingress integration"
    assert grpc_ingress_netloc == "grpc_domain"


def test_certification_integration(
    juju: jubilant.Juju,
    certificate_integration_data: dict | None,
) -> None:
    assert certificate_integration_data
    certificates = json.loads(certificate_integration_data["certificates"])
    certificate = certificates[0]["certificate"]
    assert f"CN={OPENFGA_APP}.{juju.model}.svc.cluster.local" == extract_certificate_common_name(
        certificate
    )


def test_scale_up(juju: jubilant.Juju) -> None:
    juju.cli("scale-application", OPENFGA_APP, "2")

    juju.wait(
        ready=and_(
            all_active(OPENFGA_APP, OPENFGA_CLIENT_APP),
            unit_number(app=OPENFGA_APP, expected_num=2),
        ),
        timeout=5 * 60,
    )


def test_remove_certificates_integration(juju: jubilant.Juju) -> None:
    with remove_integration(juju, CERTIFICATE_PROVIDER_APP, "certificates"):
        juju.wait(
            ready=all_active(OPENFGA_APP, OPENFGA_CLIENT_APP),
            timeout=5 * 60,
        )


def test_remove_database_integration(juju: jubilant.Juju) -> None:
    with remove_integration(juju, DB_APP, "database"):
        juju.wait(
            ready=all_blocked(OPENFGA_APP),
            timeout=5 * 60,
        )


def test_scale_down(juju: jubilant.Juju) -> None:
    juju.cli("scale-application", OPENFGA_APP, "1")

    juju.wait(
        ready=and_(
            all_active(OPENFGA_APP, OPENFGA_CLIENT_APP),
            unit_number(app=OPENFGA_APP, expected_num=1),
        ),
        timeout=5 * 60,
    )
