#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import jubilant
import pytest
import requests

from tests.integration.util import (
    DB_CHARM,
    METADATA,
    all_active,
    any_error,
    get_unit_address,
    is_active,
    is_blocked,
    or_,
)

logger = logging.getLogger(__name__)


class TestOpenFGAUpgrade:
    openfga_app_name = "openfga-upgrade"
    openfga_client_app_name = "openfga-tester-upgrade"
    postgresql_app_name = "postgresql-upgrade"

    @pytest.mark.setup
    def test_deploy_openfga_from_charmhub(
        self, juju: jubilant.Juju, openfga_tester_charm: Path
    ) -> None:
        juju.deploy(
            charm=DB_CHARM,
            app=self.postgresql_app_name,
            channel="14/stable",
            trust=True,
        )

        juju.deploy(
            charm="openfga-k8s",
            app=self.openfga_app_name,
            channel="latest/edge",
            trust=True,
        )

        juju.deploy(
            charm=openfga_tester_charm,
            app=self.openfga_client_app_name,
            trust=True,
        )

        juju.integrate(
            f"{self.openfga_app_name}:openfga", f"{self.openfga_client_app_name}:openfga"
        )
        juju.integrate(self.openfga_app_name, f"{self.postgresql_app_name}:database")

        juju.wait(
            ready=all_active(
                self.postgresql_app_name,
                self.openfga_app_name,
                self.openfga_client_app_name,
            ),
            error=any_error(
                self.postgresql_app_name,
                self.openfga_app_name,
                self.openfga_client_app_name,
            ),
        )

    def test_refresh_openfga_application(self, juju: jubilant.Juju, openfga_charm: Path) -> None:
        juju.cli(
            "refresh",
            self.openfga_app_name,
            "--path",
            str(openfga_charm),
            "--resource",
            f"oci-image={METADATA['resources']['oci-image']['upstream-source']}",
            "--trust",
        )

        juju.wait(
            ready=or_(
                is_active(self.openfga_app_name),
                is_blocked(self.openfga_app_name),
            ),
        )

    def test_run_schema_upgrade_action(self, juju: jubilant.Juju) -> None:
        juju.run(
            unit=f"{self.openfga_app_name}/0",
            action="schema-upgrade",
            wait=10 * 60,
        )

        juju.wait(
            ready=all_active(self.openfga_app_name),
        )

    def test_openfga_health_after_upgrade(
        self,
        juju: jubilant.Juju,
        http_client: requests.Session,
    ) -> None:
        unit_address = get_unit_address(juju, self.openfga_app_name)
        resp = http_client.get(f"http://{unit_address}:8080/healthz")
        resp.raise_for_status()
