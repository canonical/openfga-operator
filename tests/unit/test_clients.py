# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

import pytest

from clients import OpenFGAStore


class TestOpenFGAStore:
    @pytest.fixture
    def mocked_client(self) -> MagicMock:
        return MagicMock()

    def test_create_existing_store(self, mocked_client: MagicMock) -> None:
        mocked_client.list_stores.return_value = [
            {"id": "1", "name": "store-1"},
            {"id": "2", "name": "store-2"},
        ]

        store = OpenFGAStore(client=mocked_client)
        store_id = store.create("store-1")

        assert store_id == "1"
        mocked_client.list_stores.assert_called_once()
        mocked_client.create_store.assert_not_called()

    def test_create_store(self, mocked_client: MagicMock) -> None:
        mocked_client.list_stores.return_value = [
            {"id": "1", "name": "store-1"},
        ]
        mocked_client.create_store.return_value = "2"

        store = OpenFGAStore(client=mocked_client)
        store_id = store.create("store-2")

        assert store_id == "2"
        mocked_client.list_stores.assert_called_once()
        mocked_client.create_store.assert_called_once_with("store-2")
