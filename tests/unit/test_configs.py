# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

from configs import CharmConfig


class TestCharmConfig:
    @patch("ops.model.ConfigData", autospec=True)
    def test_to_env_vars(self, mocked_class: MagicMock) -> None:
        mocked_config = mocked_class.return_value
        mocked_config.__getitem__.side_effect = lambda key: {"log-level": "debug"}[key]
        charm_config = CharmConfig(mocked_config)

        result = charm_config.to_env_vars()
        assert result == {"OPENFGA_LOG_LEVEL": "debug"}
