# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import textwrap

REQUIRER_CHARM = textwrap.dedent(
    """
import logging
from typing import Any

from any_charm_base import AnyCharmBase
from openfga import OpenFGARequires, OpenFGAStoreCreateEvent
from ops import EventBase
from ops.charm import CharmBase
from ops.model import ActiveStatus, WaitingStatus

logger = logging.getLogger(__name__)


class AnyCharm(AnyCharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)

        self.openfga_requirer = OpenFGARequires(self, "test-openfga-store", "openfga")
        self.framework.observe(
            self.openfga_requirer.on.openfga_store_created,
            self._on_openfga_store_created,
        )

        # self.framework.observe(self.on.start, self._on_update_status)
        # self.framework.observe(self.on.config_changed, self._on_update_status)
        # self.framework.observe(self.on.update_status, self._on_update_status)

    def _on_update_status(self, event: EventBase) -> None:
        if not (info := self.openfga_requirer.get_store_info()):
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

        if not (info := self.openfga_requirer.get_store_info()):
            event.defer()
            return

        logger.info("store id {}".format(info.store_id))
        logger.info("token {}".format(info.token))
        logger.info("grpc_api_url {}".format(info.grpc_api_url))
        logger.info("http_api_url {}".format(info.http_api_url))

        self._on_update_status(event)
"""
)
