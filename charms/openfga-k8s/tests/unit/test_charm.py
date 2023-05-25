# Copyright 2022 Canonical Ltd
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import logging
import pathlib
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from charm import (
    STATE_KEY_CA,
    STATE_KEY_CERTIFICATE,
    STATE_KEY_CHAIN,
    STATE_KEY_DB_URI,
    STATE_KEY_DNS_NAME,
    STATE_KEY_PRIVATE_KEY,
    STATE_KEY_SCHEMA_CREATED,
    STATE_KEY_TOKEN,
    OpenFGAOperatorCharm,
)
from ops.testing import Harness

logger = logging.getLogger(__name__)

LOG_FILE = "/var/log/openfga-k8s"


class TestCharm(unittest.TestCase):
    @patch("charm.KubernetesServicePatch", lambda x, y: None)
    def setUp(self, *unused):
        self.harness = Harness(OpenFGAOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.disable_hooks()
        self.harness.add_oci_resource("openfga-image")
        self.harness.begin()

        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.harness.charm.framework.charm_dir = pathlib.Path(
            self.tempdir.name
        )

        self.harness.container_pebble_ready("openfga")

    @patch("charm.OpenFGAOperatorCharm._get_logrotate_config")
    def test_logrotate_config_pushed(self, get_logrotate_config: MagicMock):
        self.harness.set_leader(True)

        rel_id = self.harness.add_relation("openfga-peer", "openfga")
        self.harness.add_relation_unit(rel_id, "openfga-k8s/1")
        self.harness.update_relation_data(
            rel_id,
            "openfga-k8s",
            {
                STATE_KEY_TOKEN: "test-token",
                STATE_KEY_SCHEMA_CREATED: "true",
                STATE_KEY_DB_URI: "test-db-uri",
                STATE_KEY_PRIVATE_KEY: "test-key",
                STATE_KEY_CERTIFICATE: "test-cert",
                STATE_KEY_CA: "test-ca",
                STATE_KEY_CHAIN: "test-chain",
                STATE_KEY_DNS_NAME: "test-dns-name",
            },
        )

        container = self.harness.model.unit.get_container("openfga")
        self.harness.charm.on.openfga_pebble_ready.emit(container)
        get_logrotate_config.assert_called_once()
        

    def test_on_config_changed(self):
        self.harness.set_leader(True)

        rel_id = self.harness.add_relation("openfga-peer", "openfga")
        self.harness.add_relation_unit(rel_id, "openfga-k8s/1")
        self.harness.update_relation_data(
            rel_id,
            "openfga-k8s",
            {
                STATE_KEY_TOKEN: "test-token",
                STATE_KEY_SCHEMA_CREATED: "true",
                STATE_KEY_DB_URI: "test-db-uri",
                STATE_KEY_PRIVATE_KEY: "test-key",
                STATE_KEY_CERTIFICATE: "test-cert",
                STATE_KEY_CA: "test-ca",
                STATE_KEY_CHAIN: "test-chain",
                STATE_KEY_DNS_NAME: "test-dns-name",
            },
        )

        container = self.harness.model.unit.get_container("openfga")
        self.harness.charm.on.openfga_pebble_ready.emit(container)

        self.harness.update_config(
            {
                "log-level": "debug",
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
                        "command": "/app/openfga run | tee {LOG_FILE}",
                        "environment": {
                            "OPENFGA_AUTHN_METHOD": "preshared",
                            "OPENFGA_AUTHN_PRESHARED_KEYS": "test-token",
                            "OPENFGA_DATASTORE_ENGINE": "postgres",
                            "OPENFGA_DATASTORE_URI": "test-db-uri",
                            "OPENFGA_GRPC_TLS_CERT": "/app/certificate.pem",
                            "OPENFGA_GRPC_TLS_ENABLED": "true",
                            "OPENFGA_GRPC_TLS_KEY": "/app/key.pem",
                            "OPENFGA_HTTP_TLS_CERT": "/app/certificate.pem",
                            "OPENFGA_HTTP_TLS_ENABLED": "true",
                            "OPENFGA_HTTP_TLS_KEY": "/app/key.pem",
                            "OPENFGA_LOG_LEVEL": "debug",
                            "OPENFGA_PLAYGROUND_ENABLED": "false",
                        },
                    },
                }
            },
        )

    @patch("charm.OpenFGAOperatorCharm.create_openfga_store")
    @patch("charm.OpenFGAOperatorCharm.get_address")
    def test_on_openfga_relation_joined(
        self,
        get_address,
        create_openfga_store,
        *unused,
    ):
        create_openfga_store.return_value = "01GK13VYZK62Q1T0X55Q2BHYD6"
        get_address.return_value = "10.10.0.17"

        self.harness.set_leader(True)

        rel_id = self.harness.add_relation("openfga-peer", "openfga")
        self.harness.add_relation_unit(rel_id, "openfga-k8s/1")
        self.harness.update_relation_data(
            rel_id,
            "openfga-k8s",
            {
                STATE_KEY_TOKEN: "test-token",
                STATE_KEY_SCHEMA_CREATED: "true",
                STATE_KEY_DB_URI: "test-db-uri",
            },
        )

        self.harness.update_config(
            {
                "log-level": "debug",
            }
        )
        self.harness.charm.on.config_changed.emit()

        self.harness.enable_hooks()
        rel_id = self.harness.add_relation("openfga", "openfga-client")
        self.harness.add_relation_unit(rel_id, "openfga-client/0")

        self.harness.update_relation_data(
            rel_id,
            "openfga-client",
            {"store-name": "test-store-name"},
        )

        create_openfga_store.assert_called_with("test-store-name")
        assert self.harness.get_relation_data(rel_id, "openfga-k8s") == {
            "address": "10.10.0.17",
            "port": "8080",
            "scheme": "http",
            "token": "test-token",
            "store-id": "01GK13VYZK62Q1T0X55Q2BHYD6",
            "dns-name": "openfga-k8s-0.openfga-k8s-endpoints.None.svc.cluster.local",
        }
