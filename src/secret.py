# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Optional, ValuesView

from ops import Model, SecretNotFoundError

from constants import (
    PRESHARED_TOKEN_SECRET_KEY,
    PRESHARED_TOKEN_SECRET_LABEL,
    SECRET_ID_KEY,
)
from env_vars import EnvVars


class Secrets:
    """An abstraction of the charm secret management."""

    KEYS = (PRESHARED_TOKEN_SECRET_KEY,)
    LABELS = (PRESHARED_TOKEN_SECRET_LABEL,)

    def __init__(self, model: Model) -> None:
        self._model = model

    def __getitem__(self, label: str) -> Optional[dict[str, str]]:
        if label not in self.LABELS:
            return None

        try:
            secret = self._model.get_secret(label=label)
        except SecretNotFoundError:
            return None

        return secret.get_content(refresh=True)

    def __setitem__(self, label: str, content: dict[str, str]) -> None:
        if label not in self.LABELS:
            raise ValueError(f"Invalid label: '{label}'. Valid labels are: {self.LABELS}.")

        secret = self._model.app.add_secret(content, label=label)
        secret.set_content(content | {SECRET_ID_KEY: secret.id})

    def values(self) -> ValuesView:
        secret_contents = {}
        for key, label in zip(self.KEYS, self.LABELS):
            try:
                secret = self._model.get_secret(label=label)
            except SecretNotFoundError:
                return ValuesView({})
            else:
                secret_contents[key] = secret.get_content(refresh=True)

        return secret_contents.values()

    def to_env_vars(self) -> EnvVars:
        if not self.is_ready:
            return {}

        return {
            "OPENFGA_AUTHN_METHOD": "preshared",
            "OPENFGA_AUTHN_PRESHARED_KEYS": self[PRESHARED_TOKEN_SECRET_LABEL][
                PRESHARED_TOKEN_SECRET_KEY
            ],  # type: ignore[index]
        }

    @property
    def is_ready(self) -> bool:
        values = self.values()
        return all(values) if values else False
