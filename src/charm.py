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
from typing import Dict, Optional
from urllib.parse import urlparse

import requests
from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v0.loki_push_api import LogProxyConsumer
from charms.observability_libs.v1.kubernetes_service_patch import KubernetesServicePatch
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.traefik_k8s.v1.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from lightkube.models.core_v1 import ServicePort
from ops.charm import CharmBase, RelationChangedEvent, RelationDepartedEvent
from ops.jujuversion import JujuVersion
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, ModelError, Relation, WaitingStatus
from ops.pebble import Error, ExecError
from requests.models import Response

from constants import (
    DATABASE_NAME,
    DATABASE_RELATION_NAME,
    GRAFANA_RELATION_NAME,
    INGRESS_RELATION_NAME,
    LOG_FILE,
    LOG_PROXY_RELATION_NAME,
    METRIC_RELATION_NAME,
    OPENFGA_SERVER_GRPC_PORT,
    OPENFGA_SERVER_HTTP_PORT,
    PEER_KEY_DB_MIGRATE_VERSION,
    REQUIRED_SETTINGS,
    SERVICE_NAME,
    WORKLOAD_CONTAINER,
)
from openfga import OpenFGA
from state import State, requires_state, requires_state_setter

logger = logging.getLogger(__name__)


class OpenFGAOperatorCharm(CharmBase):
    """OpenFGA Operator Charm."""

    def __init__(self, *args):
        super().__init__(*args)

        self._state = State(self.app, lambda: self.model.get_relation("peer"))
        self._container = self.unit.get_container(WORKLOAD_CONTAINER)
        self.openfga = OpenFGA(f"http://127.0.0.1:{OPENFGA_SERVER_HTTP_PORT}", self._container)

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
        self.framework.observe(self.on.openfga_relation_changed, self._on_openfga_relation_changed)

        # Ingress relation
        self.ingress = IngressPerAppRequirer(
            self, relation_name=INGRESS_RELATION_NAME, port=OPENFGA_SERVER_HTTP_PORT
        )
        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.ingress.on.revoked, self._on_ingress_revoked)

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
        if self._container.can_connect():
            try:
                service = self._container.get_service(SERVICE_NAME)
            except ModelError:
                logger.warning("service not found, won't stop")
                return
            if service.is_running():
                self._container.stop(SERVICE_NAME)
        self.unit.status = WaitingStatus("service stopped")

    def _on_update_status(self, _):
        """Update the status of the charm."""
        self._ready()

    @property
    def _domain_name(self):
        if url := self.ingress.url:
            # Remove scheme part from url
            url = urlparse(url)
            dns_name = url.netloc + url.path
        else:
            dns_name = "{}.{}-endpoints.{}.svc.cluster.local".format(
                self.unit.name.replace("/", "-"), self.app.name, self.model.name
            )
        return dns_name

    def _get_database_relation_info(self) -> Optional[Dict]:
        """Get database info from relation data bag."""
        if not self.database.relations:
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
    def _pebble_layer(self):
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
                return {}

        return {
            "summary": "openfga layer",
            "description": "pebble layer for openfga",
            "services": {
                SERVICE_NAME: {
                    "override": "merge",
                    "summary": "OpenFGA",
                    "command": f"sh -c 'openfga run 2>&1 | tee -a {LOG_FILE}'",
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

    def _get_token(self):
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
        self._update_workload(event)

    @requires_state
    def _update_workload(self, event):
        """' Update workload with all available configuration data."""
        # make sure we can connect to the container
        if not self._container.can_connect():
            logger.info("cannot connect to the openfga container")
            event.defer()
            return

        self._create_token(event)
        if not self.model.relations[DATABASE_RELATION_NAME]:
            self.unit.status = BlockedStatus("Missing required relation with postgresql")
            return

        if not self.database.is_resource_created():
            self.unit.status = WaitingStatus("Waiting for database creation")
            return

        # check if the schema has been upgraded
        if self._migration_is_needed():
            logger.info("waiting for schema upgrade")
            self.unit.status = BlockedStatus("Please run schema-upgrade action")
            return

        # if openfga relation exists, make sure the address is
        # updated
        if self.unit.is_leader():
            openfga_relation = self.model.get_relation("openfga")
            if openfga_relation and self.app in openfga_relation.data:
                openfga_relation.data[self.app].update(
                    {
                        "address": self._get_address(openfga_relation),
                        "dns-name": self._domain_name,
                    }
                )

        self._container.add_layer("openfga", self._pebble_layer, combine=True)
        if not self._ready():
            logger.info("workload container not ready - deferring")
            event.defer()
            return

        self._container.restart(SERVICE_NAME)
        self.unit.status = ActiveStatus()

    def _on_peer_relation_changed(self, event):
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

        setattr(self._state, self._migration_peer_data_key, self.openfga.get_version())
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

        return (
            getattr(self._state, self._migration_peer_data_key, None) != self.openfga.get_version()
        )

    def _run_sql_migration(self) -> bool:
        """Runs database migration.

        Returns True if migration was run successfully, else returns false.
        """
        try:
            self.openfga.run_migration(self._dsn)
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
        if not plan.services.get(SERVICE_NAME):
            self.unit.status = WaitingStatus("waiting for service")
            return False

        env_vars = plan.services.get(SERVICE_NAME).environment
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
    def _on_openfga_relation_changed(self, event: RelationChangedEvent):
        """Open FGA relation changed."""
        # the requires side will put the store_name in its
        # application bucket
        store_name = event.relation.data[event.app].get("store_name", "")
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
        data = {
            "store_id": store_id,
            "address": self._get_address(event.relation),
            "scheme": "http",
            "port": str(OPENFGA_SERVER_HTTP_PORT),
            "dns_name": self._domain_name,
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

        address = f"http://localhost:{OPENFGA_SERVER_HTTP_PORT}"
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
        response = requests.post(
            "{}/stores".format(address),
            json={"name": store_name},
            headers=headers,
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
        if not self._container.can_connect():
            event.set_results({"error": "cannot connect to the workload container"})
            return

        if self._run_sql_migration():
            event.set_results({"result": "done"})
        else:
            event.set_results({"result": "failed to migrate database"})
            self.unit.status = BlockedStatus("Database migration job failed")
            return

        logger.info("schema upgraded")
        setattr(self._state, self._migration_peer_data_key, self.openfga.get_version())
        self._update_workload(event)

    def _on_ingress_ready(self, event: IngressPerAppReadyEvent):
        self._update_workload(event)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent):
        self._update_workload(event)


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
