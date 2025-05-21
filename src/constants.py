# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path
from string import Template

# Charm constants
DATABASE_NAME = "openfga"
POSTGRESQL_DSN_TEMPLATE = Template("postgres://$username:$password@$endpoint/$database")
WORKLOAD_CONTAINER = "openfga"
WORKLOAD_SERVICE = "openfga"
PRESHARED_TOKEN_SECRET_KEY = "token"
PRESHARED_TOKEN_SECRET_LABEL = "token"

# Application constants
OPENFGA_SERVER_HTTP_PORT = 8080
OPENFGA_METRICS_HTTP_PORT = 2112
OPENFGA_SERVER_GRPC_PORT = 8081
CA_BUNDLE_FILE = Path("/etc/ssl/certs/ca-certificates.crt")
PRIVATE_KEY_DIR = Path("/etc/ssl/private")
LOCAL_CA_CERTS_DIR = Path("/usr/local/share/ca-certificates")
SERVER_KEY = PRIVATE_KEY_DIR / "server.key"
SERVER_CERT = LOCAL_CA_CERTS_DIR / "server.crt"

# Integration constants
DATABASE_INTEGRATION_NAME = "database"
HTTP_INGRESS_INTEGRATION_NAME = "http-ingress"
GRPC_INGRESS_INTEGRATION_NAME = "grpc-ingress"
GRAFANA_INTEGRATION_NAME = "grafana-dashboard"
LOGGING_INTEGRATION_NAME = "logging"
METRIC_INTEGRATION_NAME = "metrics-endpoint"
OPENFGA_INTEGRATION_NAME = "openfga"
CERTIFICATES_INTEGRATION_NAME = "certificates"
CERTIFICATES_TRANSFER_INTEGRATION_NAME = "send-ca-cert"
PEER_INTEGRATION_NAME = "peer"
