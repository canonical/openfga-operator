# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Any, Dict, Generator, List

import pytest
from charms.openfga_k8s.v0.openfga import (
    OpenFGARequires,
    OpenFGAStoreCreateEvent,
    OpenFGAStoreRemovedEvent,
)
from ops.charm import CharmBase
from ops.framework import EventBase
from ops.testing import Harness

METADATA = """
name: requirer-tester
requires:
  openfga:
    interface: openfga
"""


class OpenFGARequiresCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.openfga = OpenFGARequires(self, "test-openfga-store")
        self.events: List = []

        self.framework.observe(self.openfga.on.openfga_store_created, self._record_event)
        self.framework.observe(self.openfga.on.openfga_store_removed, self._record_event)

    def _record_event(self, event: EventBase) -> None:
        self.events.append(event)


@pytest.fixture()
def harness() -> Generator:
    harness = Harness(OpenFGARequiresCharm, meta=METADATA)
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    yield harness
    harness.cleanup()


@pytest.fixture()
def requirer_databag() -> Dict:
    return {"store_name": "test-openfga-store"}


@pytest.fixture()
def provider_databag() -> Dict:
    return {
        "store_id": "store_id",
        "token_secret_id": "token_secret_id",
        "address": "127.0.0.1",
        "scheme": "http",
        "port": "8080",
        "dns_name": "example.domain.test.com/1234",
    }


def test_data_in_relation_bag(harness: Harness, requirer_databag: Dict) -> None:
    relation_id = harness.add_relation("openfga", "provider")

    relation_data = harness.get_relation_data(relation_id, harness.model.app.name)

    assert relation_data == requirer_databag


def test_event_emitted_when_data_available(harness: Harness, provider_databag: Dict) -> None:
    relation_id = harness.add_relation("openfga", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    harness.update_relation_data(
        relation_id,
        "provider",
        provider_databag,
    )

    events = [e for e in harness.charm.events if isinstance(e, OpenFGAStoreCreateEvent)]
    assert len(events) == 1
    assert events[0].store_id == provider_databag["store_id"]


def test_event_emitted_when_data_removed(harness: Harness, provider_databag: Dict) -> None:
    relation_id = harness.add_relation("openfga", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    harness.remove_relation(relation_id)

    events = [e for e in harness.charm.events if isinstance(e, OpenFGAStoreRemovedEvent)]
    assert len(events) == 1


def test_get_store_info_when_data_available(harness: Harness, provider_databag: Dict) -> None:
    token = "token"
    relation_id = harness.add_relation("openfga", "provider")
    secret_id = harness.add_model_secret("provider", {"token": token})
    harness.grant_secret(secret_id, "requirer-tester")
    provider_databag["token_secret_id"] = secret_id
    harness.add_relation_unit(relation_id, "provider/0")
    harness.update_relation_data(
        relation_id,
        "provider",
        provider_databag,
    )

    info = harness.charm.openfga.get_store_info()

    assert info.token == token
    assert info.store_id == provider_databag["store_id"]
    assert info.token_secret_id == provider_databag["token_secret_id"]
    assert info.address == provider_databag["address"]
    assert info.scheme == provider_databag["scheme"]
    assert info.port == provider_databag["port"]


def test_get_store_info_when_data_unavailable(harness: Harness, provider_databag: Dict) -> None:
    relation_id = harness.add_relation("openfga", "provider")
    harness.add_relation_unit(relation_id, "provider/0")

    info = harness.charm.openfga.get_store_info()

    assert info is None
