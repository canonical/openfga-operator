#!/usr/bin/env python3
# This file is part of the OpenFGA k8s Charm for Juju.
# Copyright 2022 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3, as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""OpenFGA K8S charm."""

import logging
import secrets

import requests
from charms.data_platform_libs.v0.database_requires import DatabaseEvent, DatabaseRequires
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v0.loki_push_api import LogProxyConsumer
from charms.observability_libs.v1.kubernetes_service_patch import KubernetesServicePatch
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.tls_certificates_interface.v1.tls_certificates import (
    CertificateAvailableEvent,
    CertificateExpiringEvent,
    CertificateRevokedEvent,
    TLSCertificatesRequiresV1,
    generate_csr,
    generate_private_key,
)
from charms.traefik_k8s.v1.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from lightkube.models.core_v1 import ServicePort
from ops.charm import CharmBase, RelationChangedEvent, RelationJoinedEvent
from ops.jujuversion import JujuVersion
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, ModelError, Relation, WaitingStatus
from ops.pebble import ExecError
from requests.models import Response

from state import State, requires_state, requires_state_setter

logger = logging.getLogger(__name__)

WORKLOAD_CONTAINER = "openfga"

REQUIRED_SETTINGS = [
    "OPENFGA_DATASTORE_URI",
    "OPENFGA_AUTHN_PRESHARED_KEYS",
]

LOG_FILE = "/var/log/openfga-k8s"
LOGROTATE_CONFIG_PATH = "/etc/logrotate.d/openfga"

OPENFGA_SERVER_PORT = 8080

LOG_FILE = "/var/log/openfga-k8s"
LOGROTATE_CONFIG_PATH = "/etc/logrotate.d/openfga"

OPENFGA_SERVER_PORT = 8080

SERVICE_NAME = "openfga"


class OpenFGAOperatorCharm(CharmBase):
    """OpenFGA Operator Charm."""

    def __init__(self, *args):
        super().__init__(*args)

        self._state = State(self.app, lambda: self.model.get_relation("peer"))

        self.framework.observe(self.on.openfga_pebble_ready, self._on_openfga_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.leader_elected, self._on_leader_elected)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.stop, self._on_stop)
        self.framework.observe(self.on.peer_relation_changed, self._on_peer_relation_changed)

        # Actions
        self.framework.observe(self.on.schema_upgrade_action, self._on_schema_upgrade_action)

        # Grafana dashboard relation
        self._grafana_dashboards = GrafanaDashboardProvider(
            self, relation_name="grafana-dashboard"
        )

        # Loki log-proxy relation (TODO(ale8k): Test this works properly)
        self.log_proxy = LogProxyConsumer(
            self,
            log_files=[LOG_FILE],
            relation_name="log-proxy",
            promtail_resource_name="promtail-bin",
            container_name=WORKLOAD_CONTAINER,
        )

        # Prometheus metrics endpoint relation
        self.metrics_endpoint = MetricsEndpointProvider(
            self,
            jobs=[{"static_configs": [{"targets": [f"*:{OPENFGA_SERVER_PORT}"]}]}],
            refresh_event=self.on.config_changed,
            relation_name="metrics-endpoint",
        )

        # OpenFGA relation
        self.framework.observe(self.on.openfga_relation_changed, self._on_openfga_relation_changed)

        # Certificates relation
        self.certificates = TLSCertificatesRequiresV1(self, "certificates")
        self.framework.observe(
            self.on.certificates_relation_joined,
            self._on_certificates_relation_joined,
        )
        self.framework.observe(
            self.certificates.on.certificate_available,
            self._on_certificate_available,
        )
        self.framework.observe(
            self.certificates.on.certificate_expiring,
            self._on_certificate_expiring,
        )
        self.framework.observe(
            self.certificates.on.certificate_revoked,
            self._on_certificate_revoked,
        )

        # Ingress relation
        self.ingress = IngressPerAppRequirer(self, relation_name="ingress", port=8080)
        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.ingress.on.revoked, self._on_ingress_revoked)

        # Database relation
        self.database = DatabaseRequires(
            self,
            relation_name="database",
            database_name="openfga",
        )
        self.framework.observe(self.database.on.database_created, self._on_database_event)
        self.framework.observe(
            self.database.on.endpoints_changed,
            self._on_database_event,
        )
        self.framework.observe(self.on.database_relation_broken, self._on_database_relation_broken)

        port_http = ServicePort(8080, name=f"{self.app.name}-http", protocol="TCP")
        port_grpc = ServicePort(8081, name=f"{self.app.name}-grpc", protocol="TCP")
        self.service_patcher = KubernetesServicePatch(self, [port_http, port_grpc])

    def _on_openfga_pebble_ready(self, event):
        """Workload pebble ready."""
        self._update_workload(event)

    def _on_config_changed(self, event):
        """Configuration changed."""
        self._update_workload(event)

    def _on_start(self, event):
        """Start OpenFGA."""
        self._update_workload(event)

    def _on_stop(self, _):
        """Stop OpenFGA."""
        container = self.unit.get_container(WORKLOAD_CONTAINER)
        if container.can_connect():
            try:
                service = container.get_service(SERVICE_NAME)
            except ModelError:
                logger.warning("service not found, won't stop")
                return
            if service.is_running():
                container.stop(SERVICE_NAME)
        self.unit.status = WaitingStatus("service stopped")

    def _on_update_status(self, _):
        """Update the status of the charm."""
        self._ready()

    @requires_state_setter
    def _create_token(self, event):
        token = secrets.token_urlsafe(32)
        if JujuVersion.from_environ().has_secrets:
            if not self._state.token_secret_id:
                content = {"token": token}
                secret = self.app.add_secret(content)
                self._state.token_secret_id = secret.id
                logger.info("created token secret {}".format(secret.id))
        else:
            if not self._state.token:
                self._state.token = token

    @requires_state
    def _get_token(self, event):
        if JujuVersion.from_environ().has_secrets:
            if self._state.token_secret_id:
                secret = self.model.get_secret(id=self._state.token_secret_id)
                secret_content = secret.get_content()
                return secret_content["token"]
            else:
                return None
        else:
            return self._state.token

    @requires_state_setter
    def _on_leader_elected(self, event):
        """Leader elected."""
        # generate the private key if one is not present in the
        # application data bucket of the peer relation
        if not self._state.private_key:
            private_key: bytes = generate_private_key(key_size=4096)
            self._state.private_key = private_key.decode()

        self._update_workload(event)

    # flake8: noqa: C901
    @requires_state
    def _update_workload(self, event):
        """' Update workload with all available configuration data."""
        # Quickly update logrotates config each workload update
        self._push_to_workload(LOGROTATE_CONFIG_PATH, self._get_logrotate_config(), event)

        container = self.unit.get_container(WORKLOAD_CONTAINER)
        # make sure we can connect to the container
        if not container.can_connect():
            logger.info("cannot connect to the openfga container")
            event.defer()
            return

        self._create_token(event)

        # Quickly update logrotates config each workload update
        self._push_to_workload(LOGROTATE_CONFIG_PATH, self._get_logrotate_config(), event)

        dnsname = "{}.{}-endpoints.{}.svc.cluster.local".format(
            self.unit.name.replace("/", "-"), self.app.name, self.model.name
        )
        if self._state.dns_name:
            dnsname = self._state.dns_name

        # check if the database connection string has been
        # recorded in the peer relation's application data bucket
        if not self._state.db_uri:
            logger.info("waiting for postgresql relation")
            self.unit.status = BlockedStatus("Waiting for postgresql relation")
            return

        # check if the schema has been upgraded
        if not self._state.schema_created:
            logger.info("waiting for schema upgrade")
            self.unit.status = BlockedStatus("Please run schema-upgrade action")
            return

        # if openfga relation exists, make sure the address is
        # updated
        if self.unit.is_leader():
            openfga_relation = self.model.get_relation("openfga")
            if openfga_relation and self.app in openfga_relation.data:
                old_address = openfga_relation.data[self.app].get("address", "")
                new_address = self._get_address(openfga_relation)
                if old_address != new_address:
                    openfga_relation.data[self.app].update({"address": new_address})
                old_dns = openfga_relation.data[self.app].get("dns-name")
                if old_dns != dnsname:
                    openfga_relation.data[self.app].update({"dns-name": dnsname})

        env_vars = map_config_to_env_vars(self)
        env_vars["OPENFGA_PLAYGROUND_ENABLED"] = "false"
        env_vars["OPENFGA_DATASTORE_ENGINE"] = "postgres"
        env_vars["OPENFGA_DATASTORE_URI"] = self._state.db_uri

        token = self._get_token(event)
        if token:
            env_vars["OPENFGA_AUTHN_METHOD"] = "preshared"
            env_vars["OPENFGA_AUTHN_PRESHARED_KEYS"] = token

        if self._state.certificate and self._state.private_key:
            container.push("/app/certificate.pem", self._state.certificate, make_dirs=True)
            container.push("/app/key.pem", self._state.private_key, make_dirs=True)
            env_vars["OPENFGA_HTTP_TLS_ENABLED"] = "true"
            env_vars["OPENFGA_HTTP_TLS_CERT"] = "/app/certificate.pem"
            env_vars["OPENFGA_HTTP_TLS_KEY"] = "/app/key.pem"
            env_vars["OPENFGA_GRPC_TLS_ENABLED"] = "true"
            env_vars["OPENFGA_GRPC_TLS_CERT"] = "/app/certificate.pem"
            env_vars["OPENFGA_GRPC_TLS_KEY"] = "/app/key.pem"

        env_vars = {key: value for key, value in env_vars.items() if value}
        for setting in REQUIRED_SETTINGS:
            if not env_vars.get(setting, ""):
                self.unit.status = BlockedStatus(
                    "{} configuration value not set".format(setting),
                )
                return

        pebble_layer = {
            "summary": "openfga layer",
            "description": "pebble layer for openfga",
            "services": {
                SERVICE_NAME: {
                    "override": "merge",
                    "summary": "OpenFGA",
                    "command": "sh -c '/app/openfga run | tee {LOG_FILE}'",
                    "startup": "disabled",
                    "environment": env_vars,
                }
            },
            "checks": {
                "openfga-check": {
                    "override": "replace",
                    "period": "1m",
                    "http": {"url": "http://localhost:8080/healthz"},
                }
            },
        }
        container.add_layer("openfga", pebble_layer, combine=True)
        if self._ready():
            if container.get_service(SERVICE_NAME).is_running():
                container.replan()
            else:
                container.start(SERVICE_NAME)
            self.unit.status = ActiveStatus()
            if self.unit.is_leader():
                self.app.status = ActiveStatus()
        else:
            logger.info("workload container not ready - deferring")
            event.defer()
            return

    def _on_peer_relation_changed(self, event):
        self._update_workload(event)

    @requires_state_setter
    def _on_database_event(self, event: DatabaseEvent) -> None:
        """Database event handler."""
        # get the first endpoint from a comma separate list
        ep = event.endpoints.split(",", 1)[0]
        # compose the db connection string
        uri = f"postgresql://{event.username}:{event.password}@{ep}/openfga"

        # record the connection string
        self._state.db_uri = uri

        self._update_workload(event)

    @requires_state_setter
    def _on_database_relation_broken(self, event: DatabaseEvent) -> None:
        """Database relation broken handler."""
        # when the database relation is broken, we unset the
        # connection string and schema-created from the application
        # bucket of the peer relation
        del self._state.db_uri
        del self._state.schema_created

        self._update_workload(event)

    def _ready(self) -> bool:
        container = self.unit.get_container(WORKLOAD_CONTAINER)

        if not self._state.is_ready():
            return False

        if not self._state.db_uri:
            self.unit.status = BlockedStatus("Waiting for postgresql relation")
            return False

        if not self._state.schema_created:
            self.unit.status = BlockedStatus("Please run schema-upgrade action")
            return False

        if container.can_connect():
            plan = container.get_plan()
            if plan.services.get(SERVICE_NAME) is None:
                self.unit.status = WaitingStatus("waiting for service")
                return False

            env_vars = plan.services.get(SERVICE_NAME).environment

            for setting in REQUIRED_SETTINGS:
                if not env_vars.get(setting, ""):
                    self.unit.status = BlockedStatus(
                        "{} configuration value not set".format(setting),
                    )
                    return False

            if container.get_service(SERVICE_NAME).is_running():
                self.unit.status = ActiveStatus()

            return True
        else:
            logger.debug("cannot connect to workload container")
            self.unit.status = WaitingStatus("waiting for the OpenFGA workload")
            return False

    def is_openfga_server_running(self) -> bool:
        container = self.unit.get_container(WORKLOAD_CONTAINER)
        if not container.can_connect():
            logger.error(f"Cannot connect to container {WORKLOAD_CONTAINER}")
            return False
        try:
            svc = container.get_service(SERVICE_NAME)
        except ModelError:
            logger.error(f"{SERVICE_NAME} is not running")
            return False
        if not svc.is_running():
            logger.error(f"{SERVICE_NAME} is not running")
            return False
        return True

    @requires_state_setter
    def _on_openfga_relation_changed(self, event: RelationChangedEvent):
        """Open FGA relation changed."""
        # the requires side will put the store_name in its
        # application bucket
        store_name = event.relation.data[event.app].get("store_name", "")
        if not store_name:
            return

        dnsname = "{}.{}-endpoints.{}.svc.cluster.local".format(
            self.unit.name.replace("/", "-"), self.app.name, self.model.name
        )
        if self._state.dns_name:
            dnsname = self._state.dns_name

        token = self._get_token(event)
        if not token:
            logger.error("token not found")
            event.defer()
            return

        if not self.is_openfga_server_running():
            event.defer()
            return

        store_id = self._create_openfga_store(token, store_name)
        if not store_id:
            logger.error("failed to create openfga store")
            return

        # update the relation data with information needed
        # to connect to OpenFga
        data = {
            "store_id": store_id,
            "address": self._get_address(event.relation),
            "scheme": "http",
            "port": "8080",
            "dns_name": dnsname,
        }

        if JujuVersion.from_environ().has_secrets:
            secret = self.model.get_secret(id=self._state.token_secret_id)
            secret.grant(event.relation)

            data["token_secret_id"] = self._state.token_secret_id
        else:
            data["token"] = self._state.token

        event.relation.data[self.app].update(data)

    def _get_address(self, relation: Relation):
        """Returns the ip address to be used with the specified relation."""
        return self.model.get_binding(relation).network.ingress_address.exploded

    def _create_openfga_store(self, token: str, store_name: str):
        logger.info("creating store: {}".format(store_name))

        address = "http://localhost:8080"
        headers = {"Authorization": "Bearer {}".format(token)}

        # we need to check if the store with the specified name already
        # exists, otherwise OpenFGA will happily create a new store with
        # the same name, but different id.
        stores = self._list_stores(address, headers)
        for store in stores:
            if store["name"] == store_name:
                logger.info(
                    "store {} already exists: returning store id {}".format(
                        store_name, store["id"]
                    )
                )
                return store["id"]

        # to create a new store we issue a POST request to /stores
        # endpoint
        headers["Content-Type"] = "application/json"
        response = requests.post(
            "{}/stores".format(address),
            json={"name": store_name},
            headers=headers,
            verify=False,
        )
        if response.status_code == 200 or response.status_code == 201:
            # if we successfully created the store, we return its id.
            data = response.json()
            return data["id"]

        logger.error(
            "failed to create the openfga store: {} {}".format(
                response.status_code,
                response.json(),
            )
        )
        return ""

    def _list_stores(self, openfga_host: str, headers, continuation_token="") -> list:
        # to list stores we need to issue a GET request to the /stores
        # endpoint
        response: Response = requests.get(
            "{}/stores".format(openfga_host),
            headers=headers,
            verify=False,
        )
        if response.status_code != 200:
            logger.error("to list existing openfga store: {}".format(response.json()))
            return None

        data = response.json()
        logger.info("received list stores response {}".format(data))
        stores = []
        for store in data["stores"]:
            stores.append({"id": store["id"], "name": store["name"]})

        # if the response contains a continuation_token, we
        # need an additional request to fetch all the stores
        ctoken = data["continuation_token"]
        if not ctoken:
            return stores
        else:
            return stores.append(
                self._list_stores(
                    openfga_host,
                    headers,
                    continuation_token=ctoken,
                )
            )

    @requires_state_setter
    def _on_schema_upgrade_action(self, event):
        """Performs a schema upgrade on the configurable database."""
        db_uri = self._state.db_uri
        if not db_uri:
            event.set_results({"error": "missing postgres relation"})
            return

        container = self.unit.get_container(WORKLOAD_CONTAINER)
        if not container.can_connect():
            event.set_results({"error": "cannot connect to the workload container"})
            return

        migration_process = container.exec(
            command=[
                "/app/openfga",
                "migrate",
                "--datastore-engine",
                "postgres",
                "--datastore-uri",
                "{}".format(db_uri),
            ],
            encoding="utf-8",
        )

        try:
            stdout = migration_process.wait_output()
            self.unit.status = WaitingStatus("Schema migration done")
            event.set_results({"result": "done"})
        except ExecError as e:
            if "already exists" in e.stderr:
                logger.info("schema migration failed because the schema already exists")
                self.unit.status = WaitingStatus("Schema migration done")
                event.set_results({"result": "done"})
            else:
                logger.error(
                    "failed to run schema migration: err {} db_uri {}".format(e.stderr, db_uri)
                )
                event.set_results({"std-err": e.stderr, "std-out": stdout, "db_uri": db_uri})
        self._state.schema_created = "true"

        logger.info("schema upgraded")
        self._update_workload(event)

    @requires_state_setter
    def _on_certificates_relation_joined(self, event: RelationJoinedEvent) -> None:
        dnsname = "{}.{}-endpoints.{}.svc.cluster.local".format(
            self.unit.name.replace("/", "-"), self.app.name, self.model.name
        )

        if self._state.dns_name:
            dnsname = self._state.dns_name

        private_key = self._state.private_key
        csr = generate_csr(
            private_key=private_key.encode(),
            subject=dnsname,
        )
        self._state.csr = csr.decode()

        self.certificates.request_certificate_creation(certificate_signing_request=csr)

    @requires_state_setter
    def _on_certificate_available(self, event: CertificateAvailableEvent) -> None:
        self._state.certificate = event.certificate
        self._state.ca = event.ca
        self._state.key_chain = event.chain

        self._update_workload(event)

    @requires_state_setter
    def _on_certificate_expiring(self, event: CertificateExpiringEvent) -> None:
        old_csr = self._state.csr
        private_key = self._state.private_key

        dnsname = "{}.{}-endpoints.{}.svc.cluster.local".format(
            self.unit.name.replace("/", "-"),
            self.app.name,
            self.model.name,
        )
        if self._state.dns_name:
            dnsname = self._state.dns_name

        new_csr = generate_csr(private_key=private_key.encode(), subject=dnsname)
        self.certificates.request_certificate_renewal(
            old_certificate_signing_request=old_csr,
            new_certificate_signing_request=new_csr,
        )

        self._state.csr = new_csr.decode()

        self._update_workload()

    @requires_state_setter
    def _on_certificate_revoked(self, event: CertificateRevokedEvent) -> None:
        old_csr = self._state.csr
        private_key = self._state.private_key

        dnsname = "{}.{}-endpoints.{}.svc.cluster.local".format(
            self.unit.name.replace("/", "-"),
            self.app.name,
            self.model.name,
        )
        if self._state.dns_name:
            dnsname = self._state.dns_name

        new_csr = generate_csr(
            private_key=private_key.encode(),
            subject=dnsname,
        )
        self.certificates.request_certificate_renewal(
            old_certificate_signing_request=old_csr,
            new_certificate_signing_request=new_csr,
        )

        self._state.csr = new_csr.decode()
        del self._state.certificate
        del self._state.ca
        del self._state.key_chain

        self.unit.status = WaitingStatus("Waiting for new certificate")

        self._update_workload()

    @requires_state_setter
    def _on_ingress_ready(self, event: IngressPerAppReadyEvent):
        self._state.dns_name = event.url

        self._update_workload(event)

    @requires_state_setter
    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent):
        del self._state.dns_name

        self._update_workload(event)

    def _get_logrotate_config(self):
        return f"""{LOG_FILE} {"{"}
            rotate 3
            daily
            compress
            delaycompress
            missingok
            notifempty
            size 10M
{"}"}
"""

    def _push_to_workload(self, filename, content, event):
        """Pushes file to the workload container.

        Create file on the workload container with
        the specified content.
        """
        container = self.unit.get_container(WORKLOAD_CONTAINER)
        if container.can_connect():
            logger.info("pushing file {} to the workload container".format(filename))
            container.push(filename, content, make_dirs=True)
        else:
            logger.info("workload container not ready - deferring")
            event.defer()


def map_config_to_env_vars(charm, **additional_env):
    """Map config values to environment variables.

    Maps the config values provided in config.yaml into environment
    variables such that they can be passed directly to the pebble layer.
    """
    env_mapped_config = {
        "OPENFGA_{}".format(k.replace("-", "_").upper()): v for k, v in charm.config.items()
    }

    return {**env_mapped_config, **additional_env}


if __name__ == "__main__":
    main(OpenFGAOperatorCharm)
