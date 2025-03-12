# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Any, Generator, Type

import pytest
from charms.openfga_k8s.v1.openfga import OpenFGAProvider, OpenFGAStoreRequestEvent
from ops.charm import CharmBase
from ops.framework import EventBase
from ops.testing import CharmType, Harness

METADATA = """
name: provider-tester
provides:
  openfga:
    interface: openfga
"""


@pytest.fixture
def provider_charm(provider_databag: dict) -> Type[CharmType]:
    class OpenFGAProviderCharm(CharmBase):
        def __init__(self, *args: Any) -> None:
            super().__init__(*args)
            self.openfga = OpenFGAProvider(self)
            self.events: list = []

            self.framework.observe(
                self.openfga.on.openfga_store_requested, self._on_openfga_store_requested
            )
            self.framework.observe(self.openfga.on.openfga_store_requested, self._record_event)

        def _on_openfga_store_requested(self, event: OpenFGAStoreRequestEvent) -> None:
            self.openfga.update_relation_info(
                relation_id=event.relation.id,
                **provider_databag,
            )

        def _record_event(self, event: EventBase) -> None:
            self.events.append(event)

    return OpenFGAProviderCharm


@pytest.fixture
def harness(provider_charm: Type[CharmType]) -> Generator:
    harness = Harness(provider_charm, meta=METADATA)
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    yield harness
    harness.cleanup()


def test_openfga_store_requested_emitted(harness: Harness, requirer_databag: dict) -> None:
    relation_id = harness.add_relation("openfga", "requirer")

    harness.update_relation_data(
        relation_id,
        "requirer",
        requirer_databag,
    )

    assert isinstance(harness.charm.events[0], OpenFGAStoreRequestEvent)


def test_openfga_store_requested_info_in_relation_databag(
    harness: Harness, requirer_databag: dict, provider_databag: dict
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
    harness: Harness, requirer_databag: dict, provider_databag: dict
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

    grpc_api_url = "http://grpc/new_api_url"
    http_api_url = "http://http/new_api_url"
    harness.charm.openfga.update_server_info(
        grpc_api_url=grpc_api_url,
        http_api_url=http_api_url,
    )

    relation_data = harness.get_relation_data(relation_id, harness.model.app)
    assert relation_data["grpc_api_url"] == grpc_api_url
    assert relation_data["http_api_url"] == http_api_url

    relation_data = harness.get_relation_data(relation_id_2, harness.model.app)
    assert relation_data["grpc_api_url"] == grpc_api_url
    assert relation_data["http_api_url"] == http_api_url
