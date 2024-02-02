# Copyright 2022 Canonical Ltd
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import json
import logging
from unittest.mock import MagicMock

from ops.testing import Harness

logger = logging.getLogger(__name__)

LOG_FILE_PATH = "/var/log/openfga/openfga-k8s.log"
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


def setup_ingress_relation(harness: Harness, type: str) -> int:
    relation_id = harness.add_relation(f"{type}-ingress", f"{type}-traefik")
    harness.add_relation_unit(relation_id, f"{type}-traefik/0")
    harness.update_relation_data(
        relation_id,
        f"{type}-traefik",
        {"ingress": json.dumps({"url": f"http://{type}:80/{harness.model.name}-openfga"})},
    )
    return relation_id


def setup_peer_relation(harness: Harness) -> None:
    rel_id = harness.add_relation("peer", "openfga")
    harness.add_relation_unit(rel_id, "openfga-k8s/1")


def test_on_config_changed(
    harness: Harness,
    mocked_token_urlsafe: MagicMock,
    mocked_dsn: MagicMock,
    mocked_migration_is_needed: MagicMock,
) -> None:
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
                "command": f"sh -c 'openfga run --log-format json --log-level debug 2>&1 | tee -a {LOG_FILE_PATH}'",
                "environment": {
                    "OPENFGA_AUTHN_METHOD": "preshared",
                    "OPENFGA_AUTHN_PRESHARED_KEYS": mocked_token_urlsafe.return_value,
                    "OPENFGA_DATASTORE_ENGINE": "postgres",
                    "OPENFGA_DATASTORE_URI": mocked_dsn.return_value,
                    "OPENFGA_LOG_LEVEL": "debug",
                    "OPENFGA_PLAYGROUND_ENABLED": "false",
                },
            },
        },
        "checks": {
            "openfga-http-check": {
                "override": "replace",
                "period": "1m",
                "http": {"url": "http://localhost:8080/healthz"},
            },
            "openfga-grpc-check": {
                "override": "replace",
                "period": "1m",
                "exec": {
                    "command": "grpc_health_probe -addr localhost:8081",
                },
            },
        },
    }


def test_on_openfga_relation_joined(
    harness: Harness,
    mocked_token_urlsafe: MagicMock,
    mocked_migration_is_needed: MagicMock,
    mocked_dsn: MagicMock,
    mocked_create_openfga_store: MagicMock,
) -> None:
    ip = "10.0.0.1"
    harness.add_network(ip)
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
    assert relation_data["grpc_api_url"] == f"http://{ip}:8081"
    assert relation_data["http_api_url"] == f"http://{ip}:8080"
    assert relation_data["token"] == mocked_token_urlsafe.return_value
    assert relation_data["store_id"] == mocked_create_openfga_store.return_value


def test_on_openfga_relation_joined_with_ingress(
    harness: Harness,
    mocked_token_urlsafe: MagicMock,
    mocked_migration_is_needed: MagicMock,
    mocked_dsn: MagicMock,
    mocked_create_openfga_store: MagicMock,
) -> None:
    ip = "10.0.0.1"
    harness.add_network(ip)
    harness.container_pebble_ready("openfga")
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    setup_ingress_relation(harness, "grpc")
    setup_ingress_relation(harness, "http")

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
    assert relation_data["grpc_api_url"] == f"http://{ip}:8081"
    assert relation_data["http_api_url"] == "http://http:80/openfga-model-openfga"
    assert relation_data["token"] == mocked_token_urlsafe.return_value
    assert relation_data["store_id"] == mocked_create_openfga_store.return_value


def test_on_openfga_relation_joined_with_secrets(
    harness: Harness,
    mocked_token_urlsafe: MagicMock,
    mocked_migration_is_needed: MagicMock,
    mocked_dsn: MagicMock,
    mocked_create_openfga_store: MagicMock,
    mocked_juju_version: MagicMock,
) -> None:
    ip = "10.0.0.1"
    harness.add_network(ip)
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
    assert relation_data["grpc_api_url"] == f"http://{ip}:8081"
    assert relation_data["http_api_url"] == f"http://{ip}:8080"
    assert relation_data["token_secret_id"].startswith("secret:")
    assert relation_data["store_id"] == mocked_create_openfga_store.return_value
