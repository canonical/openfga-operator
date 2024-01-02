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
from typing import Any

from charms.openfga_k8s.v1.openfga import OpenFGARequires, OpenFGAStoreCreateEvent
from ops import EventBase
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, WaitingStatus

from state import State

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)

VALID_LOG_LEVELS = ["info", "debug", "warning", "error", "critical"]


class OpenfgaRequiresCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args: Any) -> None:
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
        self.framework.observe(
            self.openfga.on.openfga_store_created,
            self._on_openfga_store_created,
        )

    def _on_update_status(self, event: EventBase) -> None:
        info = self.openfga.get_store_info()
        if not info:
            self.unit.status = WaitingStatus("waiting for store information")
            event.defer()
            return

        if info.store_id:
            self.unit.status = ActiveStatus(
                "running with store {}".format(
                    info.store_id,
                )
            )
        else:
            self.unit.status = WaitingStatus("waiting for store information")

    def _on_openfga_store_created(self, event: OpenFGAStoreCreateEvent) -> None:
        if not self.unit.is_leader():
            return

        if not event.store_id:
            return

        info = self.openfga.get_store_info()
        if not info:
            event.defer()
            return

        logger.info("store id {}".format(info.store_id))
        logger.info("token {}".format(info.token))
        logger.info("grpc_api_url {}".format(info.grpc_api_url))
        logger.info("http_api_url {}".format(info.http_api_url))

        self._on_update_status(event)


if __name__ == "__main__":  # pragma: nocover
    main(OpenfgaRequiresCharm)
