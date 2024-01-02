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
from typing import TYPE_CHECKING, Any, Dict, Optional

import requests
from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v0.loki_push_api import LogProxyConsumer
from charms.observability_libs.v1.kubernetes_service_patch import KubernetesServicePatch
from charms.openfga_k8s.v1.openfga import OpenFGAProvider, OpenFGAStoreRequestEvent
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.traefik_k8s.v2.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from lightkube.models.core_v1 import ServicePort
from ops import (
    ActionEvent,
    ConfigChangedEvent,
    HookEvent,
    LeaderElectedEvent,
    PebbleReadyEvent,
    StartEvent,
    StopEvent,
    UpdateStatusEvent,
)
from ops.charm import CharmBase, RelationChangedEvent, RelationDepartedEvent
from ops.jujuversion import JujuVersion
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, ModelError, Relation, WaitingStatus
from ops.pebble import ChangeError, Error, ExecError, Layer

from constants import (
    DATABASE_NAME,
    DATABASE_RELATION_NAME,
    GRAFANA_RELATION_NAME,
    GRPC_INGRESS_RELATION_NAME,
    HTTP_INGRESS_RELATION_NAME,
    LOG_FILE,
    LOG_PROXY_RELATION_NAME,
    METRIC_RELATION_NAME,
    OPENFGA_RELATION_NAME,
    OPENFGA_SERVER_GRPC_PORT,
    OPENFGA_SERVER_HTTP_PORT,
    PEER_KEY_DB_MIGRATE_VERSION,
    REQUIRED_SETTINGS,
    SERVICE_NAME,
    WORKLOAD_CONTAINER,
)
from openfga import OpenFGA
from state import State, requires_state, requires_state_setter

if TYPE_CHECKING:
    from ops.pebble import LayerDict

logger = logging.getLogger(__name__)


class OpenFGAOperatorCharm(CharmBase):
    """OpenFGA Operator Charm."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)

        self._state = State(self.app, lambda: self.model.get_relation("peer"))
        self._container = self.unit.get_container(WORKLOAD_CONTAINER)
        self.openfga = OpenFGA(f"http://127.0.0.1:{OPENFGA_SERVER_HTTP_PORT}", self._container)
        self.openfga_relation = OpenFGAProvider(self, relation_name=OPENFGA_RELATION_NAME)

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
            self, relation_name=GRAFANA_RELATION_NAME
        )

        # Loki log-proxy relation
        self.log_proxy = LogProxyConsumer(
            self,
            log_files=[LOG_FILE],
            relation_name=LOG_PROXY_RELATION_NAME,
            promtail_resource_name="promtail-bin",
            container_name=WORKLOAD_CONTAINER,
        )

        # Prometheus metrics endpoint relation
        self.metrics_endpoint = MetricsEndpointProvider(
            self,
            jobs=[{"static_configs": [{"targets": [f"*:{OPENFGA_SERVER_HTTP_PORT}"]}]}],
            refresh_event=self.on.config_changed,
            relation_name=METRIC_RELATION_NAME,
        )

        # OpenFGA relation
        self.framework.observe(
            self.openfga_relation.on.openfga_store_requested, self._on_openfga_store_requested
        )

        # Ingress HTTP relation
        self.http_ingress = IngressPerAppRequirer(
            self,
            relation_name=HTTP_INGRESS_RELATION_NAME,
            port=OPENFGA_SERVER_HTTP_PORT,
            strip_prefix=True,
        )
        self.framework.observe(self.http_ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.http_ingress.on.revoked, self._on_ingress_revoked)

        # Ingress GRPC relation
        self.grpc_ingress = IngressPerAppRequirer(
            self,
            relation_name=GRPC_INGRESS_RELATION_NAME,
            port=OPENFGA_SERVER_GRPC_PORT,
            strip_prefix=True,
            scheme="h2c",
        )
        self.framework.observe(self.grpc_ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.grpc_ingress.on.revoked, self._on_ingress_revoked)

        # Database relation
        self.database = DatabaseRequires(
            self,
            relation_name=DATABASE_RELATION_NAME,
            database_name=DATABASE_NAME,
        )
        self.framework.observe(self.database.on.database_created, self._on_database_created)
        self.framework.observe(
            self.database.on.endpoints_changed,
            self._on_database_changed,
        )
        self.framework.observe(self.on.database_relation_broken, self._on_database_relation_broken)

        port_http = ServicePort(
            OPENFGA_SERVER_HTTP_PORT, name=f"{self.app.name}-http", protocol="TCP"
        )
        port_grpc = ServicePort(
            OPENFGA_SERVER_GRPC_PORT, name=f"{self.app.name}-grpc", protocol="TCP"
        )
        self.service_patcher = KubernetesServicePatch(self, [port_http, port_grpc])

    def _on_openfga_pebble_ready(self, event: PebbleReadyEvent) -> None:
        """Workload pebble ready."""
        self._update_workload(event)

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Configuration changed."""
        self._update_workload(event)

    def _on_start(self, event: StartEvent) -> None:
        """Start OpenFGA."""
        self._update_workload(event)

    def _on_stop(self, _: StopEvent) -> None:
        """Stop OpenFGA."""
        if self._container.can_connect():
            try:
                service = self._container.get_service(SERVICE_NAME)
            except ModelError:
                logger.warning("service not found, won't stop")
                return
            if service.is_running():
                self._container.stop(SERVICE_NAME)
        self.unit.status = WaitingStatus("service stopped")

    def _on_update_status(self, _: UpdateStatusEvent) -> None:
        """Update the status of the charm."""
        self._ready()

    def _get_database_relation_info(self) -> Optional[Dict]:
        """Get database info from relation data bag."""
        if not self.database.is_resource_created():
            return None

        relation_id = self.database.relations[0].id
        relation_data = self.database.fetch_relation_data()[relation_id]
        return {
            "username": relation_data.get("username"),
            "password": relation_data.get("password"),
            "endpoints": relation_data.get("endpoints"),
            "database_name": DATABASE_NAME,
        }

    @property
    def _log_level(self) -> str:
        return self.config["log-level"]

    @property
    def _dsn(self) -> Optional[str]:
        db_info = self._get_database_relation_info()
        if not db_info:
            return None

        return "postgres://{username}:{password}@{endpoints}/{database_name}".format(
            username=db_info.get("username"),
            password=db_info.get("password"),
            endpoints=db_info.get("endpoints"),
            database_name=db_info.get("database_name"),
        )

    @property
    def _migration_peer_data_key(self) -> Optional[str]:
        if not self.database.relations:
            return None
        return f"{PEER_KEY_DB_MIGRATE_VERSION}_{self.database.relations[0].id}"

    @property
    def _pebble_layer(self) -> Layer:
        env_vars = map_config_to_env_vars(self)
        env_vars["OPENFGA_PLAYGROUND_ENABLED"] = "false"
        env_vars["OPENFGA_DATASTORE_ENGINE"] = "postgres"
        env_vars["OPENFGA_DATASTORE_URI"] = self._dsn

        token = self._get_token()
        if token:
            env_vars["OPENFGA_AUTHN_METHOD"] = "preshared"
            env_vars["OPENFGA_AUTHN_PRESHARED_KEYS"] = token

        env_vars = {key: value for key, value in env_vars.items() if value}
        for setting in REQUIRED_SETTINGS:
            if not env_vars.get(setting, ""):
                self.unit.status = BlockedStatus(
                    "{} configuration value not set".format(setting),
                )
                return Layer()

        pebble_layer: LayerDict = {
            "summary": "openfga layer",
            "description": "pebble layer for openfga",
            "services": {
                SERVICE_NAME: {
                    "override": "merge",
                    "summary": "OpenFGA",
                    "command": f"sh -c 'openfga run --log-format json --log-level {self._log_level} 2>&1 | tee -a {LOG_FILE}'",
                    "startup": "disabled",
                    "environment": env_vars,
                }
            },
            "checks": {
                "openfga-http-check": {
                    "override": "replace",
                    "period": "1m",
                    "http": {"url": f"http://localhost:{OPENFGA_SERVER_HTTP_PORT}/healthz"},
                },
                "openfga-grpc-check": {
                    "override": "replace",
                    "period": "1m",
                    "exec": {
                        "command": f"grpc_health_probe -addr localhost:{OPENFGA_SERVER_GRPC_PORT}",
                    },
                },
            },
        }
        return Layer(pebble_layer)

    def _create_token(self) -> None:
        if not self.unit.is_leader():
            return
        if JujuVersion.from_environ().has_secrets:
            if not self._state.token_secret_id:
                content = {"token": secrets.token_urlsafe(32)}
                secret = self.app.add_secret(content)
                self._state.token_secret_id = secret.id
                logger.info("created token secret {}".format(secret.id))
        else:
            if not self._state.token:
                self._state.token = secrets.token_urlsafe(32)

    def _get_token(self) -> Optional[str]:
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
    def _on_leader_elected(self, event: LeaderElectedEvent) -> None:
        """Leader elected."""
        self._update_workload(event)

    @requires_state
    def _update_workload(self, event: HookEvent) -> None:
        """' Update workload with all available configuration data."""
        # make sure we can connect to the container
        if not self._container.can_connect():
            logger.info("cannot connect to the openfga container")
            event.defer()
            return

        self._create_token()
        if not self.model.relations[DATABASE_RELATION_NAME]:
            self.unit.status = BlockedStatus("Missing required relation with postgresql")
            return

        if not self._dsn:
            self.unit.status = WaitingStatus("Waiting for database creation")
            return

        # check if the schema has been upgraded
        if self._migration_is_needed():
            logger.info("waiting for schema upgrade")
            self.unit.status = BlockedStatus("Please run schema-upgrade action")
            return

        # if openfga relation exists, make sure the address is updated
        self.openfga_relation.update_server_info(http_api_url=self.http_ingress.url)

        self._container.add_layer("openfga", self._pebble_layer, combine=True)
        if not self._ready():
            logger.info("workload container not ready - deferring")
            event.defer()
            return

        try:
            self._container.restart(SERVICE_NAME)
        except ChangeError as err:
            logger.error(str(err))
            self.unit.status = BlockedStatus(
                "Failed to restart the container, please consult the logs"
            )
            return
        self.unit.status = ActiveStatus()

    def _on_peer_relation_changed(self, event: RelationChangedEvent) -> None:
        self._update_workload(event)

    @requires_state_setter
    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Database event handler."""
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to container. Deferring the event.")
            self.unit.status = WaitingStatus("Waiting to connect to container")
            return

        if not self._migration_is_needed():
            self._update_workload(event)
            return

        if not self._run_sql_migration():
            self.unit.status = BlockedStatus("Database migration job failed")
            logger.error("Automigration job failed, please use the schema-upgrade action")
            return

        if not (peer_key := self._migration_peer_data_key):
            logger.error("Missing database relation")
            return

        setattr(self._state, peer_key, self.openfga.get_version())
        self._update_workload(event)

    @requires_state_setter
    def _on_database_changed(self, event: DatabaseEndpointsChangedEvent) -> None:
        """Database event handler."""
        self._update_workload(event)

    @requires_state_setter
    def _on_database_relation_broken(self, event: RelationDepartedEvent) -> None:
        """Database relation broken handler."""
        self._update_workload(event)

    def _migration_is_needed(self) -> Optional[bool]:
        if not self._state.is_ready():
            return None

        if not (key := self._migration_peer_data_key):
            return None

        return getattr(self._state, key, None) != self.openfga.get_version()

    def _run_sql_migration(self) -> bool:
        """Runs database migration.

        Returns True if migration was run successfully, else returns false.
        """
        if not (dsn := self._dsn):
            logger.info("No database integration")
            return False

        try:
            self.openfga.run_migration(dsn)
            logger.info("Successfully executed the database migration")
        except Error as e:
            err_msg = e.stderr if isinstance(e, ExecError) else e
            logger.error(f"Database migration failed: {err_msg}")
            return False
        return True

    def _ready(self) -> bool:
        if not self._state.is_ready():
            return False

        if self._migration_is_needed():
            self.unit.status = BlockedStatus("Please run schema-upgrade action")
            return False

        if not self._container.can_connect():
            logger.debug("cannot connect to workload container")
            self.unit.status = WaitingStatus("waiting for the OpenFGA workload")
            return False

        plan = self._container.get_plan()
        service = plan.services.get(SERVICE_NAME)
        if not service:
            self.unit.status = WaitingStatus("waiting for service")
            return False

        env_vars = service.environment
        for setting in REQUIRED_SETTINGS:
            if not env_vars.get(setting, ""):
                self.unit.status = BlockedStatus(
                    "{} configuration value not set".format(setting),
                )
                return False

        if self._container.get_service(SERVICE_NAME).is_running():
            self.unit.status = ActiveStatus()

        return True

    def _is_openfga_server_running(self) -> bool:
        if not self._container.can_connect():
            logger.error(f"Cannot connect to container {WORKLOAD_CONTAINER}")
            return False
        try:
            svc = self._container.get_service(SERVICE_NAME)
        except ModelError:
            logger.error(f"{SERVICE_NAME} is not running")
            return False
        if not svc.is_running():
            logger.error(f"{SERVICE_NAME} is not running")
            return False
        return True

    @requires_state_setter
    def _on_openfga_store_requested(self, event: OpenFGAStoreRequestEvent) -> None:
        """Open FGA relation changed."""
        # the requires side will put the store_name in its
        # application bucket
        if not event.relation.app:
            return
        store_name = event.store_name
        if not store_name:
            return

        token = self._get_token()
        if not token:
            logger.error("token not found")
            event.defer()
            return

        if not self._is_openfga_server_running():
            event.defer()
            return

        store_id = self._create_openfga_store(token, store_name)
        if not store_id:
            logger.error("failed to create openfga store")
            return

        # update the relation data with information needed
        # to connect to OpenFga
        if JujuVersion.from_environ().has_secrets:
            secret = self.model.get_secret(id=self._state.token_secret_id)
            secret.grant(event.relation)

            token_secret_id = self._state.token_secret_id
            token = None
        else:
            token_secret_id = None
            token = self._state.token

        self.openfga_relation.update_relation_info(
            store_id=store_id,
            http_api_url=self.http_ingress.url,
            token=token,
            token_secret_id=token_secret_id,
            relation_id=event.relation.id,
        )

    def _get_address(self, relation: Relation) -> str:
        """Returns the ip address to be used with the specified relation."""
        return self.model.get_binding(relation).network.ingress_address.exploded

    def _create_openfga_store(self, token: str, store_name: str) -> Optional[str]:
        logger.info("creating store: {}".format(store_name))

        # we need to check if the store with the specified name already
        # exists, otherwise OpenFGA will happily create a new store with
        # the same name, but different id.
        stores = self._list_stores(token)
        for store in stores:
            if store["name"] == store_name:
                logger.info(
                    "store {} already exists: returning store id {}".format(
                        store_name, store["id"]
                    )
                )
                return store["id"]

        try:
            store = self.openfga.create_store(token, store_name)
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to request OpenFGA API: {e}")
            return None

        return store["id"]

    def _list_stores(self, token: str, continuation_token: Optional[str] = None) -> list:
        # to list stores we need to issue a GET request to the /stores
        # endpoint
        data = self.openfga.list_stores(token, continuation_token=continuation_token)
        logger.debug("received list stores response {}".format(data))
        stores = [{"id": store["id"], "name": store["name"]} for store in data["stores"]]

        # if the response contains a continuation_token, we
        # need an additional request to fetch all the stores
        if ctoken := data["continuation_token"]:
            # TODO(nsklikas): Python does not support tail recursion. We should
            # gather all the stores iteratively. We need to first decide if we
            # want to keep this logic. (are stores with the same name really a problem?)
            return stores + self._list_stores(
                token,
                continuation_token=ctoken,
            )
        return stores

    @requires_state_setter
    def _on_schema_upgrade_action(self, event: ActionEvent) -> None:
        """Performs a schema upgrade on the configurable database."""
        if not self._container.can_connect():
            event.fail("Cannot connect to the workload container")
            return

        if self._run_sql_migration():
            event.set_results({"result": "done"})
        else:
            event.set_results({"result": "failed to migrate database"})
            self.unit.status = BlockedStatus("Database migration job failed")
            return

        logger.info("schema upgraded")
        if not (peer_key := self._migration_peer_data_key):
            logger.error("Missing database relation")
            return
        setattr(self._state, peer_key, self.openfga.get_version())
        self._update_workload(event)

    def _on_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        self._update_workload(event)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent) -> None:
        self._update_workload(event)


def map_config_to_env_vars(charm: CharmBase, **additional_env: str) -> Dict:
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
