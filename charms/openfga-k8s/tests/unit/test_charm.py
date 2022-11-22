# Copyright 2022 Canonical Ltd
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import pathlib
import tempfile
import unittest

from ops.testing import Harness

from charm import OpenFGAOperatorCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(OpenFGAOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.disable_hooks()
        self.harness.add_oci_resource("openfga-image")
        self.harness.begin()

        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.harness.charm.framework.charm_dir = pathlib.Path(self.tempdir.name)

        self.harness.container_pebble_ready("openfga")

    def test_on_config_changed(self):
        rel_id = self.harness.add_relation("openfga", "openfga")
        self.harness.add_relation_unit(rel_id, "openfga-k8s/1")
        self.harness.set_leader(True)

        self.harness.update_relation_data(
            rel_id,
            "openfga-k8s",
            {
                "token": "test-token",
            },
        )

        container = self.harness.model.unit.get_container("openfga")
        self.harness.charm.on.openfga_pebble_ready.emit(container)

        self.harness.update_config(
            {
                "log-level": "debug",
                "authn-oidc-audience": "test-audience",
                "authn-oidc-issuer": "test-issuer",
                "changelog-horizon-offset": 15,
                "dns-name": "test-dns-name",
                "grpc-addr": "0.0.0.0:1234",
                "http-addr": "0.0.0.0:1235",
                "http-enabled": True,
                "log-format": "test-log-format",
            }
        )
        self.harness.charm.on.config_changed.emit()

        # Emit the pebble-ready event for openfga
        self.harness.charm.on.openfga_pebble_ready.emit(container)

        plan = self.harness.get_container_pebble_plan("openfga")
        self.maxDiff = None
        self.assertEqual(
            plan.to_dict(),
            {
                "services": {
                    "openfga": {
                        "override": "merge",
                        "startup": "disabled",
                        "summary": "OpenFGA",
                        "command": "/openfga run",
                        "environment": {
                            "OPENFGA_AUTHN_METHOD": "preshared",
                            "OPENFGA_AUTHN_OIDC_AUDIENCE": "test-audience",
                            "OPENFGA_AUTHN_OIDC_ISSUER": "test-issuer",
                            "OPENFGA_AUTHN_PRESHARED_KEYS": "test-token",
                            "OPENFGA_CHANGELOG_HORIZON_OFFSET": 15,
                            "OPENFGA_DNS_NAME": "test-dns-name",
                            "OPENFGA_GRPC_ADDR": "0.0.0.0:1234",
                            "OPENFGA_HTTP_ADDR": "0.0.0.0:1235",
                            "OPENFGA_HTTP_ENABLED": True,
                            "OPENFGA_HTTP_UPSTREAM_TIMEOUT": "5s",
                            "OPENFGA_LIST_OBJECTS_DEADLINE": "3s",
                            "OPENFGA_LIST_OBJECTS_MAX_RESULTS": 1000,
                            "OPENFGA_LOG_FORMAT": "test-log-format",
                            "OPENFGA_LOG_LEVEL": "debug",
                            "OPENFGA_MAX_TUPLES_PER_WRITE": 100,
                            "OPENFGA_MAX_TYPES_PER_AUTHORIZATION_MODEL": 100,
                            "OPENFGA_RESOLVE_NODE_LIMIT": 25,
                        },
                    }
                }
            },
        )
