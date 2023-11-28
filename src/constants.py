# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Constants."""

WORKLOAD_CONTAINER = "openfga"
SERVICE_NAME = "openfga"

REQUIRED_SETTINGS = [
    "OPENFGA_DATASTORE_URI",
    "OPENFGA_AUTHN_PRESHARED_KEYS",
]

LOG_FILE = "/var/log/openfga-k8s"

OPENFGA_SERVER_HTTP_PORT = 8080
OPENFGA_SERVER_GRPC_PORT = 8081

PEER_KEY_DB_MIGRATE_VERSION = "db_migrate_version"

DATABASE_NAME = "openfga"

DATABASE_RELATION_NAME = "database"
HTTP_INGRESS_RELATION_NAME = "http-ingress"
GRPC_INGRESS_RELATION_NAME = "grpc-ingress"
GRAFANA_RELATION_NAME = "grafana-dashboard"
LOG_PROXY_RELATION_NAME = "log-proxy"
METRIC_RELATION_NAME = "metrics-endpoint"
OPENFGA_RELATION_NAME = "openfga"
