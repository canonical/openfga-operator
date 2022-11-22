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


import functools
import logging
import secrets

import pgsql
from charmhelpers.contrib.charmsupport.nrpe import NRPE
from charms.nginx_ingress_integrator.v0.ingress import IngressRequires
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

logger = logging.getLogger(__name__)

WORKLOAD_CONTAINER = "openfga"

REQUIRED_SETTINGS = ["OPENFGA_DNS_NAME", "OPENFGA_DATASTORE_URI"]


def log_event_handler(method):
    @functools.wraps(method)
    def decorated(self, event):
        logger.debug("running {}".format(method.__name__))
        try:
            return method(self, event)
        finally:
            logger.debug("completed {}".format(method.__name__))

    return decorated


class OpenFGAOperatorCharm(CharmBase):
    """OpenFGA Operator Charm."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.openfga_pebble_ready, self._on_openfga_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.leader_elected, self._on_leader_elected)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.stop, self._on_stop)
        self.framework.observe(self.on.nrpe_relation_joined, self._on_nrpe_relation_joined)

        # ingress relation
        self.ingress = IngressRequires(
            self,
            {
                "service-hostname": self.config.get("dns-name", ""),
                "service-name": self.app.name,
                "service-port": 8080,
            },
        )

        self._stored.set_default(db_uri=None)

        # database relation
        self.db = pgsql.PostgreSQLClient(self, "db")
        self.framework.observe(
            self.db.on.database_relation_joined,
            self._on_database_relation_joined,
        )
        self.framework.observe(self.db.on.master_changed, self._on_master_changed)

    @log_event_handler
    def _on_openfga_pebble_ready(self, event):
        if not self.unit.is_leader():
            return

        openfga_relation = self.model.get_relation("openfga")
        if not openfga_relation:
            return

        if "token" in openfga_relation.data[self.app]:
            # if token is already set
            # there is nothing to do.
            return

        token = secrets.token_urlsafe(32)
        openfga_relation.data[self.app].update({"token": token})
        self._update_workload(event)

    @log_event_handler
    def _on_config_changed(self, event):
        self._update_workload(event)

    @log_event_handler
    def _on_leader_elected(self, event):
        self._update_workload(event)

    @log_event_handler
    def _on_nrpe_relation_joined(self, event):
        """Connect a NRPE relation."""
        # use the nrpe library to handle the relation.
        nrpe = NRPE()
        nrpe.add_check(
            shortname="OpenFGA",
            description="check OpenFGA running",
            check_cmd="check_ps -p openfga -w 2 -c 10",
        )
        nrpe.write()

    def _update_workload(self, event):
        """' Update workload with all available configuration
        data."""
        container = self.unit.get_container(WORKLOAD_CONTAINER)
        if not container.can_connect():
            logger.info("cannot connect to the workload container - deferring the event")
            event.defer()
            return

        self.ingress.update_config({"service-hostname": self.config.get("dns-name", "")})

        env_vars = map_config_to_env_vars(self)
        if self._stored.db_uri:
            env_vars["OPENFGA_DATASTORE_ENGINE"] = "postgres"
            env_vars["OPENFGA_DATASTORE_URI"] = "postgres://{}".format(self._stored.db_uri)

        openfga_relation = self.model.get_relation("openfga")
        if openfga_relation and "token" in openfga_relation.data[self.app]:
            env_vars["OPENFGA_AUTHN_METHOD"] = "preshared"
            env_vars["OPENFGA_AUTHN_PRESHARED_KEYS"] = openfga_relation.data[self.app].get("token")

        env_vars = {key: value for key, value in env_vars.items() if value}

        pebble_layer = {
            "summary": "openfga layer",
            "description": "pebble config layer for openfga",
            "services": {
                "openfga": {
                    "override": "merge",
                    "summary": "OpenFGA",
                    "command": "/root/openfga run",
                    "startup": "disabled",
                    "environment": env_vars,
                }
            },
            "checks": {
                "openfga-check": {
                    "override": "replace",
                    "period": "1m",
                    "exec": {"command": "pgrep openfga"},
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
        else:
            logger.info("workload container not ready - deferring")
            event.defer()

    @log_event_handler
    def _on_start(self, _):
        """Start OpenFGA."""
        container = self.unit.get_container(WORKLOAD_CONTAINER)
        if container.can_connect():
            plan = container.get_plan()
            if plan.services.get("openfga") is None:
                logger.error("waiting for service")
                self.unit.status = WaitingStatus("waiting for service")
                return False

            env_vars = plan.services.get("openfga").environment
            for setting in REQUIRED_SETTINGS:
                if not env_vars.get(setting, ""):
                    self.unit.status = BlockedStatus(
                        "{} configuration value not set".format(setting),
                    )
                    return False
            container.start("openfga")

    @log_event_handler
    def _on_stop(self, _):
        """Stop OpenFGA."""
        container = self.unit.get_container(WORKLOAD_CONTAINER)
        if container.can_connect():
            container.stop()
        self._ready()

    @log_event_handler
    def _on_update_status(self, _):
        """Update the status of the charm."""
        self._ready()

    def _on_database_relation_joined(self, event: pgsql.DatabaseRelationJoinedEvent) -> None:
        """
        Handles determining if the database has finished setup, once setup is complete
        a master/standby may join / change in consequent events.
        """
        logging.info("(postgresql) RELATION_JOINED event fired.")

        if self.model.unit.is_leader():
            event.database = "openfga"
        elif event.database != "openfga":
            event.defer()

    def _on_master_changed(self, event: pgsql.MasterChangedEvent) -> None:
        """
        Handles master units of postgres joining / changing.
        The internal snap configuration is updated to reflect this.
        """
        logging.info("(postgresql) MASTER_CHANGED event fired.")

        if event.database != "openfga":
            logging.debug("Database setup not complete yet, returning.")
            return

        if event.master:
            self._stored.db_uri = str(event.master.uri)

    def _ready(self):
        container = self.unit.get_container(WORKLOAD_CONTAINER)

        if container.can_connect():
            plan = container.get_plan()
            if plan.services.get("openfga") is None:
                logger.error("waiting for service")
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
            logger.error("cannot connect to workload container")
            self.unit.status = WaitingStatus("waiting for the OpenFGA workload")
            return False

    def schema_upgrade_action(self, event):
        """
        Performs a schema upgrade on the configurable database
        """
        if not self.unit.is_leader():
            return

        container = self.unit.get_container(WORKLOAD_CONTAINER)
        if not container.can_connect():
            logger.error("cannot connect to the workload container")
            return

        if not self._stored.db_uri:
            logger.error("no relation to postgres")

        migration_process = container.exec(
            command=[
                "/root/openfga",
                "migrate",
                "--datastore-engine",
                "postgres",
                "--datastore-uri",
                "postgres://{}".format(self._stored.db_uri),
            ]
        )

        stdout, stderr = migration_process.wait_output()
        if stderr == "":
            self.unit.status = WaitingStatus("Schema migration done")
            event.set_results({"result": "done"})
        else:
            event.set_results({"stderr": stderr, "stdout": stdout})


def map_config_to_env_vars(charm, **additional_env):
    """
    Maps the config values provided in config.yaml into environment variables
    such that they can be passed directly to the pebble layer.
    """
    env_mapped_config = {
        "OPENFGA_{}".format(k.replace("-", "_").upper()): v for k, v in charm.config.items()
    }

    return {**env_mapped_config, **additional_env}


if __name__ == "__main__":
    main(OpenFGAOperatorCharm)
