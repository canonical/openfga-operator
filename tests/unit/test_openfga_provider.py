# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Any, Dict, Generator, List

import pytest
from charms.openfga_k8s.v0.openfga import OpenFGAProvider, OpenFGAStoreRequestEvent
from ops.charm import CharmBase
from ops.framework import EventBase
from ops.testing import Harness

METADATA = """
name: provider-tester
provides:
  openfga:
    interface: openfga
"""


PROVIDER_DATABAG = {
    "store_id": "store_id",
    "token_secret_id": "token_secret_id",
    "address": "127.0.0.1",
    "scheme": "http",
    "port": "8080",
    "dns_name": "example.domain.test.com/1234",
}


class OpenFGAProviderCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.openfga = OpenFGAProvider(self)
        self.events: List = []

        self.framework.observe(
            self.openfga.on.openfga_store_requested, self._on_openfga_store_requested
        )
        self.framework.observe(self.openfga.on.openfga_store_requested, self._record_event)

    def _on_openfga_store_requested(self, event: OpenFGAStoreRequestEvent) -> None:
        self.openfga.update_relation_info(relation_id=event.relation.id, **PROVIDER_DATABAG)

    def _record_event(self, event: EventBase) -> None:
        self.events.append(event)


@pytest.fixture()
def harness() -> Generator:
    harness = Harness(OpenFGAProviderCharm, meta=METADATA)
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    yield harness
    harness.cleanup()


@pytest.fixture()
def requirer_databag() -> Dict:
    return {"store_name": "test-openfga-store"}


@pytest.fixture()
def provider_databag() -> Dict:
    return PROVIDER_DATABAG


def test_openfga_store_requested_emitted(harness: Harness, requirer_databag: Dict) -> None:
    relation_id = harness.add_relation("openfga", "requirer")

    harness.update_relation_data(
        relation_id,
        "requirer",
        requirer_databag,
    )

    assert isinstance(harness.charm.events[0], OpenFGAStoreRequestEvent)


def test_openfga_store_requested_info_in_relation_databag(
    harness: Harness, requirer_databag: Dict, provider_databag: Dict
) -> None:
    relation_id = harness.add_relation("openfga", "requirer")

    harness.update_relation_data(
        relation_id,
        "requirer",
        requirer_databag,
    )
    relation_data = harness.get_relation_data(relation_id, harness.model.app.name)

    assert relation_data == provider_databag


def test_update_server_info(
    harness: Harness, requirer_databag: Dict, provider_databag: Dict
) -> None:
    relation_id = harness.add_relation("openfga", "requirer")
    relation_id_2 = harness.add_relation("openfga", "requirer2")
    harness.update_relation_data(
        relation_id,
        "requirer",
        requirer_databag,
    )
    harness.update_relation_data(
        relation_id_2,
        "requirer2",
        {"store_name": "test-openfga-store-2"},
    )
    dns_name = "other_dns_name.com"

    harness.charm.openfga.update_server_info(
        provider_databag["address"],
        provider_databag["scheme"],
        provider_databag["port"],
        dns_name,
    )

    relation_data = harness.get_relation_data(relation_id, harness.model.app.name)
    assert relation_data["dns_name"] == dns_name

    relation_data = harness.get_relation_data(relation_id_2, harness.model.app.name)
    assert relation_data["dns_name"] == dns_name
