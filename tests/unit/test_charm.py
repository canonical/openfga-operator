# Copyright 2022 Canonical Ltd
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import logging
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from ops.testing import Harness

from charm import OpenFGAOperatorCharm

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
        self.harness.charm.framework.charm_dir = pathlib.Path(self.tempdir.name)

        self.harness.container_pebble_ready("openfga")

    @patch("secrets.token_urlsafe")
    def test_on_config_changed(self, token_urlsafe):
        token_urlsafe.return_value = "a_test_secret"

        self.harness.set_leader(True)

        rel_id = self.harness.add_relation("peer", "openfga")
        self.harness.add_relation_unit(rel_id, "openfga-k8s/1")

        self.harness.charm._state.token = "test-token"
        self.harness.charm._state.schema_created = "true"
        self.harness.charm._state.db_uri = "test-db-uri"
        self.harness.charm._state.private_key = "test-key"
        self.harness.charm._state.certificate = "test-cert"
        self.harness.charm._state.ca = "test-ca"
        self.harness.charm._state.key_chain = "test-chain"
        self.harness.charm._state.dns_name = "test-dns-name"

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
        assert plan.to_dict() == {
            "services": {
                "openfga": {
                    "override": "merge",
                    "startup": "disabled",
                    "summary": "OpenFGA",
                    "command": "sh -c 'openfga run | tee {LOG_FILE}'",
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
        }

    @patch("charm.OpenFGAOperatorCharm._create_openfga_store")
    @patch("charm.OpenFGAOperatorCharm._get_address")
    @patch("secrets.token_urlsafe")
    def test_on_openfga_relation_joined(
        self,
        token_urlsafe,
        get_address,
        create_openfga_store,
        *unused,
    ):
        create_openfga_store.return_value = "01GK13VYZK62Q1T0X55Q2BHYD6"
        get_address.return_value = "10.10.0.17"
        token_urlsafe.return_value = "test-token"

        self.harness.set_leader(True)

        rel_id = self.harness.add_relation("peer", "openfga")
        self.harness.add_relation_unit(rel_id, "openfga-k8s/1")

        self.harness.charm._state.schema_created = "true"
        self.harness.charm._state.db_uri = "test_db_uri"

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
            {"store_name": "test-store-name"},
        )

        create_openfga_store.assert_called_with("test-token", "test-store-name")
        relation_data = self.harness.get_relation_data(rel_id, "openfga-k8s")
        self.assertEqual(relation_data["address"], "10.10.0.17")
        self.assertEqual(relation_data["port"], "8080")
        self.assertEqual(relation_data["scheme"], "http")
        self.assertEqual(relation_data["token"], "test-token")
        self.assertEqual(relation_data["store_id"], "01GK13VYZK62Q1T0X55Q2BHYD6")
        self.assertEqual(
            relation_data["dns_name"], "openfga-k8s-0.openfga-k8s-endpoints.None.svc.cluster.local"
        )

    @patch("charm.OpenFGAOperatorCharm._create_openfga_store")
    @patch("charm.OpenFGAOperatorCharm._get_address")
    @patch("secrets.token_urlsafe")
    @patch.dict(os.environ, {"JUJU_VERSION": "3.2.1"})
    def test_on_openfga_relation_joined_with_secrets(
        self,
        token_urlsafe,
        get_address,
        create_openfga_store,
        *unused,
    ):
        create_openfga_store.return_value = "01GK13VYZK62Q1T0X55Q2BHYD6"
        get_address.return_value = "10.10.0.17"
        token_urlsafe.return_value = "test-token"

        self.harness.set_leader(True)

        rel_id = self.harness.add_relation("peer", "openfga")
        self.harness.add_relation_unit(rel_id, "openfga-k8s/1")

        self.harness.charm._state.schema_created = "true"
        self.harness.charm._state.db_uri = "test_db_uri"

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
            {"store_name": "test-store-name"},
        )

        create_openfga_store.assert_called_with("test-token", "test-store-name")
        relation_data = self.harness.get_relation_data(rel_id, "openfga-k8s")
        self.assertEqual(relation_data["address"], "10.10.0.17")
        self.assertEqual(relation_data["port"], "8080")
        self.assertEqual(relation_data["scheme"], "http")
        self.assertRegex(relation_data["token_secret_id"], "secret:.*")
        self.assertEqual(relation_data["store_id"], "01GK13VYZK62Q1T0X55Q2BHYD6")
        self.assertEqual(
            relation_data["dns_name"], "openfga-k8s-0.openfga-k8s-endpoints.None.svc.cluster.local"
        )
