# Copyright 2022 Canonical Ltd
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import logging

from ops.testing import Harness

logger = logging.getLogger(__name__)

LOG_FILE = "/var/log/openfga-k8s"
DB_USERNAME = "test-username"
DB_PASSWORD = "test-password"
DB_ENDPOINT = "postgresql-k8s-primary.namespace.svc.cluster.local:5432"


def setup_postgres_relation(harness: Harness) -> int:
    db_relation_id = harness.add_relation("database", "postgresql-k8s")
    harness.add_relation_unit(db_relation_id, "postgresql-k8s/0")
    harness.update_relation_data(
        db_relation_id,
        "postgresql-k8s",
        {
            "data": '{"database": "hydra", "extra-user-roles": "SUPERUSER"}',
            "endpoints": DB_ENDPOINT,
            "password": DB_PASSWORD,
            "username": DB_USERNAME,
        },
    )

    return db_relation_id


def setup_peer_relation(harness: Harness) -> None:
    rel_id = harness.add_relation("peer", "openfga")
    harness.add_relation_unit(rel_id, "openfga-k8s/1")


def test_on_config_changed(harness, mocked_token_urlsafe, mocked_dsn, mocked_migration_is_needed):
    harness.container_pebble_ready("openfga")
    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    harness.update_config(
        {
            "log-level": "debug",
        }
    )
    harness.charm.on.config_changed.emit()

    plan = harness.get_container_pebble_plan("openfga")
    assert plan.to_dict() == {
        "services": {
            "openfga": {
                "override": "merge",
                "startup": "disabled",
                "summary": "OpenFGA",
                "command": f"sh -c 'openfga run 2>&1 | tee -a {LOG_FILE}'",
                "environment": {
                    "OPENFGA_AUTHN_METHOD": "preshared",
                    "OPENFGA_AUTHN_PRESHARED_KEYS": mocked_token_urlsafe.return_value,
                    "OPENFGA_DATASTORE_ENGINE": "postgres",
                    "OPENFGA_DATASTORE_URI": mocked_dsn.return_value,
                    "OPENFGA_LOG_LEVEL": "debug",
                    "OPENFGA_PLAYGROUND_ENABLED": "false",
                },
            },
        }
    }


def test_on_openfga_relation_joined(
    harness,
    mocked_token_urlsafe,
    mocked_migration_is_needed,
    mocked_dsn,
    mocked_get_address,
    mocked_create_openfga_store,
):
    harness.container_pebble_ready("openfga")
    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    rel_id = harness.add_relation("openfga", "openfga-client")
    harness.add_relation_unit(rel_id, "openfga-client/0")

    harness.update_relation_data(
        rel_id,
        "openfga-client",
        {"store_name": "test-store-name"},
    )

    mocked_create_openfga_store.assert_called_with(
        mocked_token_urlsafe.return_value, "test-store-name"
    )
    relation_data = harness.get_relation_data(rel_id, "openfga-k8s")
    assert relation_data["address"] == mocked_get_address.return_value
    assert relation_data["port"] == "8080"
    assert relation_data["scheme"] == "http"
    assert relation_data["token"] == mocked_token_urlsafe.return_value
    assert relation_data["store_id"] == mocked_create_openfga_store.return_value
    assert (
        relation_data["dns_name"]
        == "openfga-k8s-0.openfga-k8s-endpoints.openfga-model.svc.cluster.local"
    )


def test_on_openfga_relation_joined_with_secrets(
    harness: Harness,
    mocked_token_urlsafe,
    mocked_migration_is_needed,
    mocked_dsn,
    mocked_get_address,
    mocked_create_openfga_store,
    mocked_juju_version,
):
    harness.container_pebble_ready("openfga")
    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    rel_id = harness.add_relation("openfga", "openfga-client")
    harness.add_relation_unit(rel_id, "openfga-client/0")

    harness.update_relation_data(
        rel_id,
        "openfga-client",
        {"store_name": "test-store-name"},
    )

    mocked_create_openfga_store.assert_called_with(
        mocked_token_urlsafe.return_value, "test-store-name"
    )
    relation_data = harness.get_relation_data(rel_id, "openfga-k8s")
    assert relation_data["address"] == mocked_get_address.return_value
    assert relation_data["port"] == "8080"
    assert relation_data["scheme"] == "http"
    assert relation_data["token_secret_id"].startswith("secret:")
    assert relation_data["store_id"] == mocked_create_openfga_store.return_value
    assert (
        relation_data["dns_name"]
        == "openfga-k8s-0.openfga-k8s-endpoints.openfga-model.svc.cluster.local"
    )
