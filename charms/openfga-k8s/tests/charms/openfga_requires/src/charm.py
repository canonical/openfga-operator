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

from charms.openfga_k8s.v0.openfga import (
    OpenFGARequires,
    OpenFGAStoreCreateEvent,
)
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, WaitingStatus

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)

VALID_LOG_LEVELS = ["info", "debug", "warning", "error", "critical"]


class OpenfgaRequiresCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)

        self.framework.observe(self.on.start, self._on_update_status)
        self.framework.observe(self.on.config_changed, self._on_update_status)
        self.framework.observe(self.on.update_status, self._on_update_status)

        self.openfga = OpenFGARequires(self, "test-openfga-store")
        self.framework.observe(
            self.openfga.on.openfga_store_created,
            self._on_openfga_store_created,
        )

    def _on_update_status(self, _):
        if self.unit.is_leader():
            self.app.status = ActiveStatus("running")
        self.unit.status = ActiveStatus("running")

        openfga_relation = self.model.get_relation("openfga-test-peer")
        if openfga_relation:
            if "store-id" in openfga_relation.data[self.app]:
                self.unit.status = ActiveStatus(
                    "running with store {}".format(
                        openfga_relation.data[self.app].get("store-id")
                    )
                )

    def _on_openfga_store_created(self, event: OpenFGAStoreCreateEvent):
        if not self.unit.is_leader():
            return

        if not event.store_id:
            return

        logger.info("store id {}".format(event.store_id))
        logger.info("token {}".format(event.token))
        logger.info("address {}".format(event.address))
        logger.info("port {}".format(event.port))
        logger.info("scheme {}".format(event.scheme))

        openfga_relation = self.model.get_relation("openfga-test-peer")
        if not openfga_relation:
            event.defer()
        openfga_relation.data[self.app].update(
            {
                "store-id": event.store_id,
                "token": event.token,
                "address": event.address,
                "port": event.port,
                "scheme": event.scheme,
            }
        )


if __name__ == "__main__":  # pragma: nocover
    main(OpenfgaRequiresCharm)
