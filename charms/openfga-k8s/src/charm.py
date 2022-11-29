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
from charms.nginx_ingress_integrator.v0.ingress import IngressRequires
from ops.charm import CharmBase, RelationChangedEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, ModelError, WaitingStatus
from ops.pebble import ExecError
from requests.models import Response

logger = logging.getLogger(__name__)

WORKLOAD_CONTAINER = "openfga"

REQUIRED_SETTINGS = ["OPENFGA_DNS_NAME", "OPENFGA_DATASTORE_URI"]


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
        self.framework.observe(
            self.on.openfga_relation_changed, self._on_openfga_relation_changed
        )

        # Actions
        self.framework.observe(
            self.on.schema_upgrade_action, self.on_schema_upgrade_action
        )

        # ingress relation
        self.ingress = IngressRequires(
            self,
            {
                "service-hostname": self.config.get("dns-name", ""),
                "service-name": self.app.name,
                "service-port": 8080,
            },
        )

        # database relation
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

    def _on_openfga_pebble_ready(self, event):
        self._update_workload(event)

    def _on_config_changed(self, event):
        self._update_workload(event)

    def _on_start(self, event):
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
        if not self.unit.is_leader():
            return

        openfga_relation = self.model.get_relation("openfga-peer")
        if not openfga_relation:
            event.defer()

        if "token" in openfga_relation.data[self.app]:
            # if token is already set
            # there is nothing to do.
            return

        token = secrets.token_urlsafe(32)
        openfga_relation.data[self.app].update({"token": token})
        self._update_workload(event)

    def _update_workload(self, event):
        """' Update workload with all available configuration
        data."""
        container = self.unit.get_container(WORKLOAD_CONTAINER)
        if not container.can_connect():
            logger.info(
                "cannot connect to the workload container - deferring the event"
            )
            event.defer()
            return

        if not self.get_db_uri():
            logger.info("waiting for postgresql relation")
            self.unit.status = BlockedStatus("Waiting for postgresql relation")
            return

        if not self.schema_upgraded():
            logger.info("waiting for schema upgrade")
            self.unit.status = BlockedStatus(
                "Please run schema-upgrade action"
            )
            return

        self.ingress.update_config(
            {"service-hostname": self.config.get("dns-name", "")}
        )

        env_vars = map_config_to_env_vars(self)
        env_vars["OPENFGA_PLAYGROUND_ENABLED"] = "false"
        env_vars["OPENFGA_DATASTORE_ENGINE"] = "postgres"
        env_vars["OPENFGA_DATASTORE_URI"] = self.get_db_uri()

        peer_relation = self.model.get_relation("openfga-peer")
        if peer_relation and "token" in peer_relation.data[self.app]:
            env_vars["OPENFGA_AUTHN_METHOD"] = "preshared"
            env_vars["OPENFGA_AUTHN_PRESHARED_KEYS"] = peer_relation.data[
                self.app
            ].get("token")

        env_vars = {key: value for key, value in env_vars.items() if value}
        for setting in REQUIRED_SETTINGS:
            if not env_vars.get(setting, ""):
                self.unit.status = BlockedStatus(
                    "{} configuration value not set".format(setting),
                )
                return

        pebble_layer = {
            "summary": "openfga layer",
            "description": "pebble config layer for openfga",
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
            self.unit.status = ActiveStatus("running")
            if self.unit.is_leader():
                self.app.status = ActiveStatus("running")
        else:
            logger.info("workload container not ready - deferring")
            event.defer()

    def _on_database_event(self, event: DatabaseEvent) -> None:
        # Handles the created database

        logger.info("Postgresql database created {}".format(event))

        ep = event.endpoints.split(",", 1)[0]
        uri = f"postgresql://{event.username}:{event.password}@{ep}/openfga"
        logger.info("received postgresql uri {}".format(uri))
        self.set_db_uri(uri)
        self._update_workload(event)

    def _ready(self):
        container = self.unit.get_container(WORKLOAD_CONTAINER)

        if not self.get_db_uri():
            self.unit.status = BlockedStatus("Waiting for postgresql relation")
            return

        if not self.schema_upgraded():
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
                self.unit.status = ActiveStatus("running")
            else:
                self.unit.status = WaitingStatus("stopped")
            return True
        else:
            logger.debug("cannot connect to workload container")
            self.unit.status = WaitingStatus(
                "waiting for the OpenFGA workload"
            )
            return False

    def _on_openfga_relation_changed(self, event: RelationChangedEvent):
        """Connect a OpenFGA relation."""
        if not self.unit.is_leader():
            return

        if not self._ready():
            event.defer()
            return

        token = ""
        peer_relation = self.model.get_relation("openfga-peer")
        if peer_relation and "token" in peer_relation.data[self.app]:
            token = peer_relation.data[self.app].get("token")
        else:
            event.defer()
            return
        store_name = event.relation.data[event.app].get("store-name", "")
        if not store_name:
            return
        store_id = self.create_openfga_store(store_name)
        if not store_id:
            logger.error("failed to create the openfga store")
            return

        data = {
            "store-id": store_id,
            "token": token,
            "address": self.get_address(event),
            "scheme": "http",
            "port": self.config.get("http-addr").rsplit(":", 1)[1],
        }
        logger.info("setting openfga relation data {}".format(data))
        event.relation.data[self.app].update(data)

    def get_address(self, event: RelationChangedEvent):
        return self.model.get_binding(
            event.relation
        ).network.ingress_address.exploded

    def create_openfga_store(self, store_name: str):
        logger.info("creating store: {}".format(store_name))

        port = self.config.get("http-addr").split(":", 1)[1]
        address = "http://localhost:{}".format(port)

        headers = {}

        openfga_relation = self.model.get_relation("openfga-peer")
        if openfga_relation:
            if "token" in openfga_relation.data[self.app]:
                api_token = openfga_relation.data[self.app].get("token")
                headers = {"Authorization": "Bearer {}".format(api_token)}

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

        headers["Content-Type"] = "application/json"
        response = requests.post(
            "{}/stores".format(address),
            json={"name": store_name},
            headers=headers,
        )
        if response.status_code != 200:
            logger.error(
                "failed to create the openfga store: {}".format(
                    response.json()
                )
            )
            return ""
        data = response.json()
        return data["id"]

    def list_stores(
        self, openfga_host: str, headers, continuation_token=""
    ) -> list:
        response: Response = requests.get(
            "{}/stores".format(openfga_host),
            headers=headers,
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

        openfga_relation = self.model.get_relation("openfga-peer")
        if not openfga_relation:
            event.set_results({"error": "waiting for peer relation"})
            return

        db_uri = self.get_db_uri()
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

        if "schema-migration-ran" in openfga_relation.data[self.app]:
            return

        openfga_relation.data[self.app].update(
            {"schema-migration-ran": "true"}
        )

        logger.info("schema upgraded")
        self._update_workload(event)

    def schema_upgraded(self):
        openfga_relation = self.model.get_relation("openfga-peer")
        if not openfga_relation:
            logger.debug("schema-upgraded: no openfga relation")
            return False

        if "schema-migration-ran" in openfga_relation.data[self.app]:
            logger.debug(
                "schema-upgraded: peer relation data contains schema-migration-ran"
            )
            return True

        logger.debug(
            "schema-upgraded: peer relation data does not contain schema-migration-ran"
        )
        return False

    def set_db_uri(self, db_uri):
        if not self.unit.is_leader():
            return

        openfga_relation = self.model.get_relation("openfga-peer")
        if openfga_relation:
            openfga_relation.data[self.app].update({"db-uri": db_uri})

    def get_db_uri(self):
        openfga_relation = self.model.get_relation("openfga-peer")
        if not openfga_relation:
            return ""

        if self.app in openfga_relation.data:
            db_uri = openfga_relation.data[self.app].get("db-uri", "")
            return db_uri
        return ""

    def set_app_store(self, appName: str, storeName: str):
        if not self.unit.is_leader():
            return

        openfga_relation = self.model.get_relation("openfga-peer")
        if openfga_relation:
            openfga_relation.data[self.app].update({appName: storeName})

    def get_app_store(self, appName: str) -> str:
        if not self.unit.is_leader():
            return ""
        openfga_relation = self.model.get_relation("openfga-peer")
        if not openfga_relation:
            return ""

        return openfga_relation.data[self.app].get(appName, "")


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
