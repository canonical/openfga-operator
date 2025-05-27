# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from types import TracebackType
from typing import Optional, Type

import requests
from typing_extensions import Self

logger = logging.getLogger(__name__)


class HTTPClient:
    def __init__(self, base_url: str, auth_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth_token = auth_token
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {auth_token}"})
        self._session.verify = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: TracebackType,
    ) -> None:
        self._session.close()

    def create_store(self, store_name: str) -> str:
        try:
            resp = self._session.post(f"{self._base_url}/stores", json={"name": store_name})
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error("Failed to create OpenFGA store: %s", e)
            return ""

        return resp.json()["id"]

    def list_stores(self, continuation_token: Optional[str] = None) -> list[dict]:
        try:
            resp = self._session.get(
                f"{self._base_url}/stores",
                params={"continuation_token": continuation_token} if continuation_token else {},
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error("Failed to get OpenFGA stores: %s", e)
            return []

        stores = resp.json()["stores"]
        if continuation_token := resp.json()["continuation_token"]:
            stores.extend(self.list_stores(continuation_token))

        return stores


class OpenFGAStore:
    def __init__(self, client: HTTPClient) -> None:
        self._client = client

    def create(self, name: str) -> str:
        stores = self._client.list_stores()
        for store in stores:
            if store["name"] == name:
                logger.info("Store %s already exists: returning store id %s", name, store["id"])
                return store["id"]

        return self._client.create_store(name)
