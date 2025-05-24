# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, create_autospec

import pytest
from ops import Model, SecretNotFoundError

from constants import PRESHARED_TOKEN_SECRET_KEY, PRESHARED_TOKEN_SECRET_LABEL
from secret import Secrets


class TestSecrets:
    @pytest.fixture
    def mocked_model(self) -> MagicMock:
        return create_autospec(Model)

    @pytest.fixture
    def secrets(self, mocked_model: MagicMock) -> Secrets:
        return Secrets(mocked_model)

    def test_get(self, mocked_model: MagicMock, secrets: Secrets) -> None:
        mocked_secret = MagicMock()
        mocked_secret.get_content.return_value = {PRESHARED_TOKEN_SECRET_KEY: "foo"}
        mocked_model.get_secret.return_value = mocked_secret

        content = secrets[PRESHARED_TOKEN_SECRET_LABEL]

        assert content == {PRESHARED_TOKEN_SECRET_KEY: "foo"}
        mocked_model.get_secret.assert_called_once_with(label=PRESHARED_TOKEN_SECRET_LABEL)

    def test_get_with_invalid_label(self, secrets: Secrets) -> None:
        content = secrets["invalid_label"]
        assert content is None

    def test_get_with_secret_not_found(self, mocked_model: MagicMock, secrets: Secrets) -> None:
        mocked_model.get_secret.side_effect = SecretNotFoundError()

        content = secrets[PRESHARED_TOKEN_SECRET_LABEL]
        assert content is None

    def test_set(self, mocked_model: MagicMock, secrets: Secrets) -> None:
        content = {PRESHARED_TOKEN_SECRET_KEY: "foo"}
        secrets[PRESHARED_TOKEN_SECRET_LABEL] = content

        mocked_model.app.add_secret.assert_called_once_with(
            content, label=PRESHARED_TOKEN_SECRET_LABEL
        )

    def test_set_with_invalid_label(self, secrets: Secrets) -> None:
        with pytest.raises(ValueError):
            secrets["invalid-label"] = {PRESHARED_TOKEN_SECRET_KEY: "foo"}

    def test_values(self, mocked_model: MagicMock, secrets: Secrets) -> None:
        mocked_secret = MagicMock()
        mocked_secret.get_content.return_value = {PRESHARED_TOKEN_SECRET_KEY: "foo"}
        mocked_model.get_secret.return_value = mocked_secret

        actual = list(secrets.values())
        assert actual == [{PRESHARED_TOKEN_SECRET_KEY: "foo"}]

    def test_values_without_secret_found(self, mocked_model: MagicMock, secrets: Secrets) -> None:
        mocked_model.get_secret.side_effect = SecretNotFoundError()

        actual = list(secrets.values())
        assert not actual
