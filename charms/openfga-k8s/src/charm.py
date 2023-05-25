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


import logging
import secrets

import requests
from charms.data_platform_libs.v0.database_requires import (
    DatabaseEvent,
    DatabaseRequires,
)
from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
)
from charms.tls_certificates_interface.v1.tls_certificates import (
    CertificateAvailableEvent,
    CertificateExpiringEvent,
    CertificateRevokedEvent,
    TLSCertificatesRequiresV1,
    generate_csr,
    generate_private_key,
)

from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v0.loki_push_api import LogProxyConsumer
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider

from charms.traefik_k8s.v1.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from lightkube.models.core_v1 import ServicePort
from ops.charm import CharmBase, RelationChangedEvent, RelationJoinedEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, Relation, WaitingStatus
from ops.pebble import ExecError
from requests.models import Response
from state import PeerRelationState, RelationNotReadyError

logger = logging.getLogger(__name__)

WORKLOAD_CONTAINER = "openfga"

REQUIRED_SETTINGS = ["OPENFGA_DATASTORE_URI"]

STATE_KEY_CA = "ca"
STATE_KEY_CERTIFICATE = "certificate"
STATE_KEY_CHAIN = "chain"
STATE_KEY_CSR = "csr"
STATE_KEY_DB_URI = "db-uri"
STATE_KEY_DNS_NAME = "dns-name"
STATE_KEY_PRIVATE_KEY = "private-key"
STATE_KEY_SCHEMA_CREATED = "schema-created"
STATE_KEY_TOKEN = "openfga-token"


class OpenFGAOperatorCharm(CharmBase):
    """OpenFGA Operator Charm."""

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(
            self.on.openfga_pebble_ready, self._on_openfga_pebble_ready
        )
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.leader_elected, self._on_leader_elected)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.stop, self._on_stop)

        # Actions
        self.framework.observe(
            self.on.schema_upgrade_action, self.on_schema_upgrade_action
        )

        # OpenFGA relation
        self.framework.observe(
            self.on.openfga_relation_changed, self._on_openfga_relation_changed
        )

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
        self.ingress = IngressPerAppRequirer(
            self, relation_name="ingress", port=8080
        )
        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(
            self.ingress.on.revoked, self._on_ingress_revoked
        )

        # Database relation
        self.database = DatabaseRequires(
            self,
            relation_name="database",
            database_name="openfga",
        )
        self.framework.observe(
            self.database.on.database_created, self._on_database_event
        )
        self.framework.observe(
            self.database.on.endpoints_changed,
            self._on_database_event,
        )
        self.framework.observe(
            self.on.database_relation_broken, self._on_database_relation_broken
        )

        portHTTP = ServicePort(
            8080, name=f"{self.app.name}-http", protocol="TCP"
        )
        portGRPC = ServicePort(
            8081, name=f"{self.app.name}-grpc", protocol="TCP"
        )
        self.service_patcher = KubernetesServicePatch(
            self, [portHTTP, portGRPC]
        )

        self.state = PeerRelationState(self.model, self.app, "openfga-peer")

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
            container.stop("openfga")
        self._ready()

    def _on_update_status(self, _):
        """Update the status of the charm."""

        self._ready()

    def _on_leader_elected(self, event):
        """Leader elected."""
        if self.unit.is_leader():
            try:
                # generate token if one is not present in the application
                # data bucket of the peer relation
                if not self.state.get(STATE_KEY_TOKEN):
                    token = secrets.token_urlsafe(32)
                    self.state.set(STATE_KEY_TOKEN, token)

                # generate the private key if one is not present in the
                # application data bucket of the peer relation
                if not self.state.get(STATE_KEY_PRIVATE_KEY):
                    private_key: bytes = generate_private_key(key_size=4096)
                    self.state.set(STATE_KEY_PRIVATE_KEY, private_key.decode())

            except RelationNotReadyError:
                event.defer()
                return
        self._update_workload(event)

    def _update_workload(self, event):
        """' Update workload with all available configuration
        data."""

        container = self.unit.get_container(WORKLOAD_CONTAINER)
        # make sure we can connect to the container
        if not container.can_connect():
            logger.info("cannot connect to the openfga container")
            event.defer()
            return

        dnsname = "{}.{}-endpoints.{}.svc.cluster.local".format(
            self.unit.name.replace("/", "-"), self.app.name, self.model.name
        )
        try:
            if self.state.get(STATE_KEY_DNS_NAME):
                dnsname = self.state.get(STATE_KEY_DNS_NAME)

            # check if the database connection string has been
            # recorded in the peer relation's application data bucket
            if not self.state.get(STATE_KEY_DB_URI):
                logger.info("waiting for postgresql relation")
                self.unit.status = BlockedStatus(
                    "Waiting for postgresql relation"
                )
                return

            # check if the schema has been upgraded
            if not self.state.get(STATE_KEY_SCHEMA_CREATED):
                logger.info("waiting for schema upgrade")
                self.unit.status = BlockedStatus(
                    "Please run schema-upgrade action"
                )
                return
        except RelationNotReadyError:
            event.defer()
            return

        # if openfga relation exists, make sure the address is
        # updated
        if self.unit.is_leader():
            openfga_relation = self.model.get_relation("openfga")
            if openfga_relation and self.app in openfga_relation.data:
                old_address = openfga_relation.data[self.app].get(
                    "address", ""
                )
                new_address = self.get_address(openfga_relation)
                if old_address != new_address:
                    openfga_relation.data[self.app].update(
                        {"address": new_address}
                    )
                old_dns = openfga_relation.data[self.app].get("dns-name")
                if old_dns != dnsname:
                    openfga_relation.data[self.app].update(
                        {"dns-name": dnsname}
                    )

        env_vars = map_config_to_env_vars(self)
        env_vars["OPENFGA_PLAYGROUND_ENABLED"] = "false"
        env_vars["OPENFGA_DATASTORE_ENGINE"] = "postgres"
        env_vars["OPENFGA_DATASTORE_URI"] = self.state.get(STATE_KEY_DB_URI)

        token = ""
        try:
            token = self.state.get(STATE_KEY_TOKEN)
            if token:
                env_vars["OPENFGA_AUTHN_METHOD"] = "preshared"
                env_vars["OPENFGA_AUTHN_PRESHARED_KEYS"] = self.state.get(
                    STATE_KEY_TOKEN
                )

            certificate = self.state.get(STATE_KEY_CERTIFICATE)
            key = self.state.get(STATE_KEY_PRIVATE_KEY)
            if certificate and key:
                container.push(
                    "/app/certificate.pem", certificate, make_dirs=True
                )
                container.push("/app/key.pem", key, make_dirs=True)
                env_vars["OPENFGA_HTTP_TLS_ENABLED"] = "true"
                env_vars["OPENFGA_HTTP_TLS_CERT"] = "/app/certificate.pem"
                env_vars["OPENFGA_HTTP_TLS_KEY"] = "/app/key.pem"
                env_vars["OPENFGA_GRPC_TLS_ENABLED"] = "true"
                env_vars["OPENFGA_GRPC_TLS_CERT"] = "/app/certificate.pem"
                env_vars["OPENFGA_GRPC_TLS_KEY"] = "/app/key.pem"
        except RelationNotReadyError:
            logger.info("could not information from the peer relation state")

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
                "openfga": {
                    "override": "merge",
                    "summary": "OpenFGA",
                    "command": "/app/openfga run",
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
            if container.get_service("openfga").is_running():
                container.replan()
            else:
                container.start("openfga")
            self.unit.status = ActiveStatus()
            if self.unit.is_leader():
                self.app.status = ActiveStatus()
        else:
            logger.info("workload container not ready - deferring")
            event.defer()
            return

    def _on_database_event(self, event: DatabaseEvent) -> None:
        """Database event handler."""

        # get the first endpoint from a comma separate list
        ep = event.endpoints.split(",", 1)[0]
        # compose the db connection string
        uri = f"postgresql://{event.username}:{event.password}@{ep}/openfga"

        # record the connection string
        try:
            self.state.set(STATE_KEY_DB_URI, uri)
        except RelationNotReadyError:
            event.defer()
            return

        self._update_workload(event)

    def _on_database_relation_broken(self, event: DatabaseEvent) -> None:
        """Database relation broken handler."""

        # when the database relation is broken, we unset the
        # connection string and schema-created from the application
        # bucket of the peer relation
        try:
            self.state.unset(STATE_KEY_DB_URI, STATE_KEY_SCHEMA_CREATED)
        except RelationNotReadyError:
            event.defer()
            return
        self._update_workload(event)

    def _ready(self):
        container = self.unit.get_container(WORKLOAD_CONTAINER)

        if not self.state.get(STATE_KEY_DB_URI):
            self.unit.status = BlockedStatus("Waiting for postgresql relation")
            return

        if not self.state.get(STATE_KEY_SCHEMA_CREATED):
            self.unit.status = BlockedStatus(
                "Please run schema-upgrade action"
            )
            return

        if container.can_connect():
            plan = container.get_plan()
            if plan.services.get("openfga") is None:
                self.unit.status = WaitingStatus("waiting for service")
                return False

            env_vars = plan.services.get("openfga").environment

            for setting in REQUIRED_SETTINGS:
                if not env_vars.get(setting, ""):
                    self.unit.status = BlockedStatus(
                        "{} configuration value not set".format(setting),
                    )
                    return False

            if container.get_service("openfga").is_running():
                self.unit.status = ActiveStatus()

            return True
        else:
            logger.debug("cannot connect to workload container")
            self.unit.status = WaitingStatus(
                "waiting for the OpenFGA workload"
            )
            return False

    def _on_openfga_relation_changed(self, event: RelationChangedEvent):
        """OpenFGA relation changed."""

        if not self.unit.is_leader():
            return

        if not self._ready():
            event.defer()
            return

        # the requires side will put the store-name in its
        # application bucket
        store_name = event.relation.data[event.app].get("store-name", "")
        if not store_name:
            return

        token = ""
        dnsname = "{}.{}-endpoints.{}.svc.cluster.local".format(
            self.unit.name.replace("/", "-"), self.app.name, self.model.name
        )
        store_id = ""
        try:
            t = self.state.get(STATE_KEY_TOKEN)
            if t:
                token = t

            dns = self.state.get(STATE_KEY_DNS_NAME)
            if dns:
                dnsname = dns

            logger.info("creating store {}".format(store_name))
            store_id = self.create_openfga_store(store_name)
        except RelationNotReadyError:
            event.defer()
            return

        if not store_id:
            logger.error("failed to create the openfga store")
            return

        # update the relation data with information needed
        # to connect to OpenFga
        data = {
            "store-id": store_id,
            "token": token,
            "address": self.get_address(event.relation),
            "scheme": "http",
            "port": "8080",
        }
        if dnsname:
            data["dns-name"] = dnsname

        logger.info("setting openfga relation data {}".format(data))
        event.relation.data[self.app].update(data)

    def get_address(self, relation: Relation):
        """get_address will return the ip address to be used
        with the specified relation."""

        return self.model.get_binding(
            relation
        ).network.ingress_address.exploded

    def create_openfga_store(self, store_name: str):
        logger.info("creating store: {}".format(store_name))

        address = "http://localhost:8080"

        headers = {}

        token = self.state.get(STATE_KEY_TOKEN)
        if token:
            headers = {"Authorization": "Bearer {}".format(token)}

        # we need to check if the store with the specified name already
        # exists, otherwise OpenFGA will happily create a new store with
        # the same name, but different id.
        stores = self.list_stores(address, headers)
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

    def list_stores(
        self, openfga_host: str, headers, continuation_token=""
    ) -> list:
        # to list stores we need to issue a GET request to the /stores
        # endpoint
        response: Response = requests.get(
            "{}/stores".format(openfga_host),
            headers=headers,
            verify=False,
        )
        if response.status_code != 200:
            logger.error(
                "to list existing openfga store: {}".format(response.json())
            )
            return None

        data = response.json()
        logger.info("received list stores response {}".format(data))
        stores = []
        for store in data["stores"]:
            stores.append({"id": store["id"], "name": store["name"]})

        # if the response containes a continuation_token, we
        # need an additional request to fetch all the stores
        ctoken = data["continuation_token"]
        if not ctoken:
            return stores
        else:
            return stores.append(
                self.list_stores(
                    openfga_host,
                    headers,
                    continuation_token=ctoken,
                )
            )

    def on_schema_upgrade_action(self, event):
        """
        Performs a schema upgrade on the configurable database
        """
        if not self.unit.is_leader():
            event.set_results({"error": "unit is not the leader"})
            return

        db_uri = ""
        try:
            db_uri = self.state.get(STATE_KEY_DB_URI)
        except RelationNotReadyError:
            event.defer()
            return

        if not db_uri:
            event.set_results({"error": "missing postgres relation"})
            return

        container = self.unit.get_container(WORKLOAD_CONTAINER)
        if not container.can_connect():
            event.set_results(
                {"error": "cannot connect to the workload container"}
            )
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
                logger.info(
                    "schema migration failed because the schema already exists"
                )
                self.unit.status = WaitingStatus("Schema migration done")
                event.set_results({"result": "done"})
            else:
                logger.error(
                    "failed to run schema migration: err {} db_uri {}".format(
                        e.stderr, db_uri
                    )
                )
                event.set_results(
                    {"std-err": e.stderr, "std-out": stdout, "db_uri": db_uri}
                )

        try:
            self.state.set(STATE_KEY_SCHEMA_CREATED, "true")
        except RelationNotReadyError:
            event.defer()
            return

        logger.info("schema upgraded")
        self._update_workload(event)

    def _on_certificates_relation_joined(
        self, event: RelationJoinedEvent
    ) -> None:
        if not self.unit.is_leader():
            return

        peer_relation = self.model.get_relation("openfga-peer")
        if not peer_relation:
            self.unit.status = WaitingStatus(
                "Waiting for peer relation to be created"
            )
            event.defer()
            return

        dnsname = "{}.{}-endpoints.{}.svc.cluster.local".format(
            self.unit.name.replace("/", "-"), self.app.name, self.model.name
        )
        try:
            if self.state.get(STATE_KEY_DNS_NAME):
                dnsname = self.state.get(STATE_KEY_DNS_NAME)

            private_key = self.state.get(STATE_KEY_PRIVATE_KEY)
            csr = generate_csr(
                private_key=private_key.encode(),
                subject=dnsname,
            )
            self.state.set(STATE_KEY_CSR, csr.decode())
        except RelationNotReadyError:
            event.defer()
            return

        self.certificates.request_certificate_creation(
            certificate_signing_request=csr
        )

    def _on_certificate_available(
        self, event: CertificateAvailableEvent
    ) -> None:
        if not self.unit.is_leader():
            try:
                self.state.set(STATE_KEY_CERTIFICATE, event.certificate)
                self.state.set(STATE_KEY_CA, event.ca)
                self.state.set(STATE_KEY_CHAIN, event.chain)
            except RelationNotReadyError:
                event.defer()
                return
        self._update_workload(event)

    def _on_certificate_expiring(
        self, event: CertificateExpiringEvent
    ) -> None:
        if not self.unit.is_leader():
            old_csr = ""
            private_key = ""
            try:
                old_csr = self.state.get(STATE_KEY_CSR)
                private_key = self.state.get(STATE_KEY_PRIVATE_KEY)
            except RelationNotReadyError:
                event.defer()
                return

            dnsname = "{}.{}-endpoints.{}.svc.cluster.local".format(
                self.unit.name.replace("/", "-"),
                self.app.name,
                self.model.name,
            )
            if self.state.get(STATE_KEY_DNS_NAME):
                dnsname = self.state.get(STATE_KEY_DNS_NAME)

            new_csr = generate_csr(
                private_key=private_key.encode(), subject=dnsname
            )
            self.certificates.request_certificate_renewal(
                old_certificate_signing_request=old_csr,
                new_certificate_signing_request=new_csr,
            )
            try:
                self.state.set(STATE_KEY_CSR, new_csr.decode())
            except RelationNotReadyError:
                event.defer()
                return

        self._update_workload()

    def _on_certificate_revoked(self, event: CertificateRevokedEvent) -> None:
        if not self.unit.is_leader():
            old_csr = ""
            private_key = ""
            try:
                old_csr = self.state.get(STATE_KEY_CSR)
                private_key = self.state.get(STATE_KEY_PRIVATE_KEY)

                dnsname = "{}.{}-endpoints.{}.svc.cluster.local".format(
                    self.unit.name.replace("/", "-"),
                    self.app.name,
                    self.model.name,
                )
                if self.state.get(STATE_KEY_DNS_NAME):
                    dnsname = self.state.get(STATE_KEY_DNS_NAME)

                new_csr = generate_csr(
                    private_key=private_key.encode(),
                    subject=dnsname,
                )
                self.certificates.request_certificate_renewal(
                    old_certificate_signing_request=old_csr,
                    new_certificate_signing_request=new_csr,
                )

                self.state.set(STATE_KEY_CSR, new_csr.decode())
                self.state.unset(
                    STATE_KEY_CERTIFICATE, STATE_KEY_CA, STATE_KEY_CHAIN
                )
            except RelationNotReadyError:
                event.defer()
                return

        self.unit.status = WaitingStatus("Waiting for new certificate")

        self._update_workload()

    def _on_ingress_ready(self, event: IngressPerAppReadyEvent):
        if self.unit.is_leader():
            try:
                self.state.set(STATE_KEY_DNS_NAME, event.url)
            except RelationNotReadyError:
                event.defer()
                return

        self._update_workload(event)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent):
        if self.unit.is_leader():
            try:
                self.state.unset(STATE_KEY_DNS_NAME)
            except RelationNotReadyError:
                event.defer()
                return

        self._update_workload(event)


def map_config_to_env_vars(charm, **additional_env):
    """
    Maps the config values provided in config.yaml into environment variables
    such that they can be passed directly to the pebble layer.
    """
    env_mapped_config = {
        "OPENFGA_{}".format(k.replace("-", "_").upper()): v
        for k, v in charm.config.items()
    }

    return {**env_mapped_config, **additional_env}


if __name__ == "__main__":
    main(OpenFGAOperatorCharm)
