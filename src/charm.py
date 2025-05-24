#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""A Juju charm for OpenFGA."""

import logging
from secrets import token_urlsafe
from typing import Any

from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    K8sResourcePatchFailedEvent,
    KubernetesComputeResourcesPatch,
    ResourceRequirements,
    adjust_resource_requirements,
)
from charms.openfga_k8s.v1.openfga import OpenFGAProvider, OpenFGAStoreRequestEvent
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from charms.tls_certificates_interface.v4.tls_certificates import CertificateAvailableEvent
from charms.traefik_k8s.v2.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRevokedEvent,
)
from ops import (
    ActionEvent,
    ConfigChangedEvent,
    HookEvent,
    LeaderElectedEvent,
    PebbleReadyEvent,
    StartEvent,
)
from ops.charm import CharmBase, RelationChangedEvent, RelationDepartedEvent, RelationJoinedEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import Error, Layer

from cli import CommandLine
from clients import HTTPClient, OpenFGAStore
from configs import CharmConfig
from constants import (
    CERTIFICATES_TRANSFER_INTEGRATION_NAME,
    DATABASE_INTEGRATION_NAME,
    DATABASE_NAME,
    GRAFANA_INTEGRATION_NAME,
    LOGGING_INTEGRATION_NAME,
    METRIC_INTEGRATION_NAME,
    OPENFGA_INTEGRATION_NAME,
    OPENFGA_METRICS_HTTP_PORT,
    OPENFGA_SERVER_HTTP_PORT,
    PEER_INTEGRATION_NAME,
    PRESHARED_TOKEN_SECRET_KEY,
    PRESHARED_TOKEN_SECRET_LABEL,
    SECRET_ID_KEY,
    WORKLOAD_CONTAINER,
)
from exceptions import MigrationError, PebbleServiceError
from integrations import (
    CertificatesIntegration,
    CertificatesTransferIntegration,
    DatabaseConfig,
    GRPCIngressIntegration,
    HttpIngressIntegration,
    PeerData,
    TracingData,
)
from secret import Secrets
from services import PebbleService, WorkloadService
from utils import container_connectivity, leader_unit, peer_integration_exists

logger = logging.getLogger(__name__)


class OpenFGAOperatorCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)

        self.peer_data = PeerData(self.model)
        self.secrets = Secrets(self.model)
        self.charm_config = CharmConfig(self.config)

        self._container = self.unit.get_container(WORKLOAD_CONTAINER)
        self._workload_service = WorkloadService(self.unit)
        self._pebble_service = PebbleService(self.unit)
        self._cli = CommandLine(self._container)

        # Lifecycle event handlers
        self.framework.observe(self.on.openfga_pebble_ready, self._on_openfga_pebble_ready)
        self.framework.observe(self.on.leader_elected, self._on_leader_elected)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.peer_relation_changed, self._on_peer_relation_changed)

        # Database integration
        self.database_requirer = DatabaseRequires(
            self,
            relation_name=DATABASE_INTEGRATION_NAME,
            database_name=DATABASE_NAME,
        )
        self.framework.observe(
            self.database_requirer.on.database_created,
            self._on_database_created,
        )
        self.framework.observe(
            self.database_requirer.on.endpoints_changed,
            self._on_database_changed,
        )
        self.framework.observe(
            self.on.database_relation_broken,
            self._on_database_relation_broken,
        )

        # OpenFGA integration
        self.openfga_provider = OpenFGAProvider(self, relation_name=OPENFGA_INTEGRATION_NAME)
        self.framework.observe(
            self.openfga_provider.on.openfga_store_requested,
            self._on_openfga_store_requested,
        )

        # Certificates integration
        self._certs_integration = CertificatesIntegration(self)
        self.framework.observe(
            self._certs_integration.cert_requirer.on.certificate_available,
            self._on_cert_changed,
        )

        # HTTP ingress integration
        self.http_ingress_integration = HttpIngressIntegration(self)
        self.framework.observe(
            self.http_ingress_integration.ingress_requirer.on.ready,
            self._on_ingress_ready,
        )
        self.framework.observe(
            self.http_ingress_integration.ingress_requirer.on.revoked,
            self._on_ingress_revoked,
        )

        # GRPC ingress integration
        self.grpc_ingress_integration = GRPCIngressIntegration(self)
        self.framework.observe(
            self.grpc_ingress_integration.ingress_requirer.on.ready,
            self._on_ingress_ready,
        )
        self.framework.observe(
            self.grpc_ingress_integration.ingress_requirer.on.revoked,
            self._on_ingress_revoked,
        )

        # Certificate transfer integration
        self._certs_transfer_integration = CertificatesTransferIntegration(self)
        self.framework.observe(
            self.on[CERTIFICATES_TRANSFER_INTEGRATION_NAME].relation_joined,
            self._on_certificates_transfer_relation_joined,
        )

        # Grafana dashboard integration
        self._grafana_dashboards = GrafanaDashboardProvider(
            self, relation_name=GRAFANA_INTEGRATION_NAME
        )

        # Loki logging integration
        self._log_forwarder = LogForwarder(self, relation_name=LOGGING_INTEGRATION_NAME)

        # Prometheus metrics integration
        self.metrics_endpoint = MetricsEndpointProvider(
            self,
            jobs=[
                {
                    "metrics_path": "/metrics",
                    "static_configs": [{"targets": [f"*:{OPENFGA_METRICS_HTTP_PORT}"]}],
                }
            ],
            refresh_event=self.on.config_changed,
            relation_name=METRIC_INTEGRATION_NAME,
        )

        # Tracing integration
        self.tracing_requirer = TracingEndpointRequirer(self, protocols=["otlp_grpc"])
        self.framework.observe(
            self.tracing_requirer.on.endpoint_changed, self._on_tracing_endpoint_changed
        )
        self.framework.observe(
            self.tracing_requirer.on.endpoint_removed, self._on_tracing_endpoint_changed
        )

        # Resources patching
        self.resources_patch = KubernetesComputeResourcesPatch(
            self,
            WORKLOAD_CONTAINER,
            resource_reqs_func=self._resource_reqs_from_config,
        )
        self.framework.observe(
            self.resources_patch.on.patch_failed, self._on_resource_patch_failed
        )

        # Actions
        self.framework.observe(self.on.schema_upgrade_action, self._on_schema_upgrade_action)

    @property
    def _pebble_layer(self) -> Layer:
        database_config = DatabaseConfig.load(self.database_requirer)
        tracing_data = TracingData.load(self.tracing_requirer)
        return self._pebble_service.render_pebble_layer(
            self.charm_config,
            self._certs_integration,
            self.secrets,
            database_config,
            tracing_data,
        )

    @property
    def migration_needed(self) -> bool:
        if not peer_integration_exists(self):
            return False

        database_config = DatabaseConfig.load(self.database_requirer)
        return self.peer_data[database_config.migration_version] != self._workload_service.version

    def _on_leader_elected(self, event: LeaderElectedEvent) -> None:
        if not self.secrets.is_ready:
            self.secrets[PRESHARED_TOKEN_SECRET_LABEL] = {
                PRESHARED_TOKEN_SECRET_KEY: token_urlsafe(32)
            }

        self._holistic_handler(event)

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        self._holistic_handler(event)

    def _on_start(self, event: StartEvent) -> None:
        self._holistic_handler(event)

    def _on_openfga_pebble_ready(self, event: PebbleReadyEvent) -> None:
        if not container_connectivity(self):
            self.unit.status = WaitingStatus("Container is not connected yet")
            event.defer()
            return

        self._workload_service.open_ports()

        service_version = self._workload_service.version
        self._workload_service.version = service_version

        self._holistic_handler(event)

    def _on_peer_relation_changed(self, event: RelationChangedEvent) -> None:
        self._holistic_handler(event)

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        if not container_connectivity(self):
            self.unit.status = WaitingStatus("Container is not connected yet")
            event.defer()
            return

        if not peer_integration_exists(self):
            self.unit.status = WaitingStatus(f"Missing integration {PEER_INTEGRATION_NAME}")
            event.defer()
            return

        if not self.migration_needed:
            self._holistic_handler(event)
            return

        if not self.unit.is_leader():
            logger.info(
                "Unit does not have leadership. Wait for leader unit to run the migration."
            )
            self.unit.status = WaitingStatus("Waiting for leader unit to run the migration")
            event.defer()
            return

        try:
            self._cli.migrate(DatabaseConfig.load(self.database_requirer).dsn)
        except MigrationError:
            self.unit.status = BlockedStatus("Database migration failed")
            logger.error("Auto migration job failed. Please use the schema-upgrade action")
            return

        migration_version = DatabaseConfig.load(self.database_requirer).migration_version
        self.peer_data[migration_version] = self._workload_service.version

        self._holistic_handler(event)

    def _on_database_changed(self, event: DatabaseEndpointsChangedEvent) -> None:
        self._holistic_handler(event)

    def _on_database_relation_broken(self, event: RelationDepartedEvent) -> None:
        self._holistic_handler(event)

    @leader_unit
    def _on_openfga_store_requested(self, event: OpenFGAStoreRequestEvent) -> None:
        if not (store_name := event.store_name):
            return

        if not self.secrets.is_ready:
            logger.error("Missing required OpenFGA API token")
            event.defer()
            return

        if not self.database_requirer.is_resource_created():
            event.defer()
            return

        if not self._workload_service.is_running:
            logger.error("OpenFGA server is not running")
            event.defer()
            return

        token = self.secrets[PRESHARED_TOKEN_SECRET_LABEL][PRESHARED_TOKEN_SECRET_KEY]
        with HTTPClient(
            base_url=f"{self._certs_integration.uri_scheme}://127.0.0.1:{OPENFGA_SERVER_HTTP_PORT}",
            auth_token=token,
        ) as client:
            if not (store_id := OpenFGAStore(client).create(store_name)):
                logger.error("Failed to create OpenFGA store %s", store_name)
                return

        token_secret_id = self.secrets[PRESHARED_TOKEN_SECRET_LABEL][SECRET_ID_KEY]
        self.model.get_secret(id=token_secret_id).grant(event.relation)
        self.openfga_provider.update_relation_info(
            store_id=store_id,
            http_api_url=self.http_ingress_integration.url,
            grpc_api_url=self.grpc_ingress_integration.url,
            token=token,
            token_secret_id=token_secret_id,
            relation_id=event.relation.id,
        )

    def _on_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        self._holistic_handler(event)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent) -> None:
        self._holistic_handler(event)

    def _on_cert_changed(self, event: CertificateAvailableEvent) -> None:
        if not self._workload_service.is_running:
            event.defer()
            return

        self._holistic_handler(event)
        self._certs_transfer_integration.transfer_certificates(
            self._certs_integration.cert_data,
        )

    def _on_certificates_transfer_relation_joined(self, event: RelationJoinedEvent) -> None:
        if not self._certs_integration.tls_enabled:
            event.defer()
            return

        self._certs_transfer_integration.transfer_certificates(
            self._certs_integration.cert_data, event.relation.id
        )

    def _on_tracing_endpoint_changed(self, event: HookEvent) -> None:
        self._holistic_handler(event)

    def _on_resource_patch_failed(self, event: K8sResourcePatchFailedEvent) -> None:
        logger.error("Failed to patch resource constraints: %s", event.message)
        self.unit.status = BlockedStatus(event.message)

    def _resource_reqs_from_config(self) -> ResourceRequirements:
        requests = {"cpu": "100m", "memory": "200Mi"}
        limits = {"cpu": self.model.config.get("cpu"), "memory": self.model.config.get("memory")}
        return adjust_resource_requirements(limits, requests, adhere_to_requests=True)

    def _holistic_handler(self, event: HookEvent) -> None:
        if not container_connectivity(self):
            self.unit.status = WaitingStatus("Container is not connected yet")
            event.defer()
            return

        if not peer_integration_exists(self):
            self.unit.status = WaitingStatus(f"Missing peer integration {PEER_INTEGRATION_NAME}")
            event.defer()
            return

        if not self.model.relations[DATABASE_INTEGRATION_NAME]:
            self.unit.status = BlockedStatus(f"Missing integration {DATABASE_INTEGRATION_NAME}")
            return

        if not self.database_requirer.is_resource_created():
            self.unit.status = WaitingStatus("Waiting for database creation")
            return

        if self.migration_needed:
            self.unit.status = BlockedStatus(
                "Waiting for migration to run, try running the `schema-upgrade` action"
            )
            return

        try:
            self._certs_integration.update_certificates()
        except Error:
            self.unit.status = BlockedStatus(
                "Failed to update the TLS certificates, please check the logs"
            )
            return

        try:
            self._pebble_service.plan(self._pebble_layer)
        except PebbleServiceError:
            logger.error("Failed to start the service, please check the container logs")
            self.unit.status = BlockedStatus(
                f"Failed to restart the service, please check the {WORKLOAD_CONTAINER} logs"
            )
            return

        self.unit.status = ActiveStatus()

        self.openfga_provider.update_server_info(
            http_api_url=self.http_ingress_integration.url,
            grpc_api_url=self.grpc_ingress_integration.url,
        )

    def _on_schema_upgrade_action(self, event: ActionEvent) -> None:
        if not container_connectivity(self):
            event.fail("Cannot connect to the workload container")
            return

        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        event.log("Start migrating the database")
        try:
            self._cli.migrate(DatabaseConfig.load(self.database_requirer).dsn, timeout=120)
        except MigrationError as err:
            event.fail(f"Database migration failed: {err}")
            self.unit.status = BlockedStatus("Database migration failed")
            return

        event.log("Successfully migrated the database")

        migration_version = DatabaseConfig.load(self.database_requirer).migration_version
        self.peer_data[migration_version] = self._workload_service.version
        event.log("Successfully updated migration version")

        self._holistic_handler(event)


if __name__ == "__main__":
    main(OpenFGAOperatorCharm)
