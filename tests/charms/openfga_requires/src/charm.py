#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path
from typing import Any

import requests
from charms.certificate_transfer_interface.v0.certificate_transfer import (
    CertificateAvailableEvent,
    CertificateTransferRequires,
)
from charms.openfga_k8s.v1.openfga import OpenFGARequires, OpenFGAStoreCreateEvent
from ops import EventBase, main
from ops.charm import CharmBase
from ops.model import ActiveStatus, WaitingStatus

logger = logging.getLogger(__name__)


class OpenfgaRequiresCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)

        self.framework.observe(self.on.start, self._on_update_status)
        self.framework.observe(self.on.config_changed, self._on_update_status)
        self.framework.observe(self.on.update_status, self._on_update_status)

        self.openfga = OpenFGARequires(self, "test-openfga-store")
        self.framework.observe(
            self.openfga.on.openfga_store_created,
            self._on_openfga_store_created,
        )

        self.certificate_transfer = CertificateTransferRequires(
            self,
            relationship_name="receive-ca-cert",
        )
        self.framework.observe(
            self.certificate_transfer.on.certificate_available,
            self._on_certificate_available,
        )

    def _on_update_status(self, event: EventBase) -> None:
        if not (info := self.openfga.get_store_info()):
            self.unit.status = WaitingStatus("waiting for store information")
            event.defer()
            return

        if not info.store_id:
            self.unit.status = WaitingStatus("waiting for store information")
            return

        self.unit.status = ActiveStatus(f"running with store {info.store_id}")

    def _on_openfga_store_created(self, event: OpenFGAStoreCreateEvent) -> None:
        if not self.unit.is_leader():
            return

        if not event.store_id:
            return

        if not (info := self.openfga.get_store_info()):
            event.defer()
            return

        logger.info("OpenFGA store id: %s", info.store_id)
        logger.info("OpenFGA token: %s", info.token)
        logger.info("OpenFGA GRPC API url: %s", info.grpc_api_url)
        logger.info("OpenFGA HTTP API url: %s", info.http_api_url)

        self._on_update_status(event)

    def _on_certificate_available(self, event: CertificateAvailableEvent) -> None:
        tls_cert_dir = Path("/usr/local/share/ca-certificates/")
        logger.info("Writing TLS certificate chain to directory `%s`", tls_cert_dir)

        tls_cert_dir.mkdir(mode=0o644, exist_ok=True)
        ca_cert = tls_cert_dir / "ca-certificates.crt"
        ca_cert.write_text(event.ca)

        url = f"https://openfga.{self.model.name}.svc.cluster.local:8080/healthz"
        try:
            response = requests.get(url, verify=str(ca_cert), timeout=5)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error("OpenFGA health request failed: %s", e)
            raise


if __name__ == "__main__":
    main(OpenfgaRequiresCharm)
