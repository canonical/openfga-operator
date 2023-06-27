#!/usr/bin/env python3
# Copyright 2022 Ales Stimec
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

    https://discourse.charmhub.io/t/4208
"""

import logging

from charms.openfga_k8s.v0.openfga import OpenFGARequires, OpenFGAStoreCreateEvent
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from state import State

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)

VALID_LOG_LEVELS = ["info", "debug", "warning", "error", "critical"]


class OpenfgaRequiresCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)

        self._state = State(self.app, lambda: self.model.get_relation("openfga-test-peer"))

        self.framework.observe(self.on.start, self._on_update_status)
        self.framework.observe(self.on.config_changed, self._on_update_status)
        self.framework.observe(self.on.update_status, self._on_update_status)

        self.openfga = OpenFGARequires(self, "test-openfga-store")
        self.framework.observe(
            self.openfga.on.openfga_store_created,
            self._on_openfga_store_created,
        )

    def _on_update_status(self, event):
        if not self._state.is_ready():
            event.defer()
            return

        if self._state.store_id:
            self.unit.status = ActiveStatus(
                "running with store {}".format(
                    self._state.store_id,
                )
            )
        else:
            self.unit.status = WaitingStatus("waiting for store information")

    def _on_openfga_store_created(self, event: OpenFGAStoreCreateEvent):
        if not self.unit.is_leader():
            return

        if not self._state.is_ready():
            event.defer()
            return

        if not event.store_id:
            return

        logger.info("store id {}".format(event.store_id))
        logger.info("token_secret_id {}".format(event.token_secret_id))
        logger.info("address {}".format(event.address))
        logger.info("port {}".format(event.port))
        logger.info("scheme {}".format(event.scheme))

        if event.token_secret_id:
            secret = self.model.get_secret(id=event.token_secret_id)
            content = secret.get_content()
            logger.info("secret content {}".format(content))

        self._state.store_id = event.store_id
        self._state.token_secret_id = event.token_secret_id
        self._state.address = event.address
        self._state.port = event.port
        self._state.scheme = event.scheme


if __name__ == "__main__":  # pragma: nocover
    main(OpenfgaRequiresCharm)
