# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Constants."""

from pathlib import Path

WORKLOAD_CONTAINER = "openfga"
SERVICE_NAME = "openfga"

REQUIRED_SETTINGS = [
    "OPENFGA_DATASTORE_URI",
    "OPENFGA_AUTHN_PRESHARED_KEYS",
]


OPENFGA_SERVER_HTTP_PORT = 8080
OPENFGA_METRICS_HTTP_PORT = 2112
OPENFGA_SERVER_GRPC_PORT = 8081

PEER_KEY_DB_MIGRATE_VERSION = "db_migrate_version"

DATABASE_NAME = "openfga"

DATABASE_RELATION_NAME = "database"
HTTP_INGRESS_RELATION_NAME = "http-ingress"
GRPC_INGRESS_RELATION_NAME = "grpc-ingress"
GRAFANA_RELATION_NAME = "grafana-dashboard"
LOGGING_RELATION_NAME = "logging"
METRIC_RELATION_NAME = "metrics-endpoint"
OPENFGA_RELATION_NAME = "openfga"
CERTIFICATES_INTEGRATION_NAME = "certificates"

CA_BUNDLE_FILE = Path("/etc/ssl/certs/ca-certificates.crt")
PRIVATE_KEY_DIR = Path("/etc/ssl/private")
LOCAL_CA_CERTS_DIR = Path("/usr/local/share/ca-certificates")

SERVER_KEY = PRIVATE_KEY_DIR / "server.key"
SERVER_CERT = LOCAL_CA_CERTS_DIR / "server.crt"
