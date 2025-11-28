# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

import pytest
from ops import testing
from pytest_mock import MockerFixture

from charm import OpenFGAOperatorCharm
from constants import WORKLOAD_CONTAINER
from exceptions import MigrationError
from integrations import DatabaseConfig


class TestSchemaUpgradeAction:
    @pytest.fixture(autouse=True)
    def mocked_database_config(self, mocker: MockerFixture) -> DatabaseConfig:
        mocked = mocker.patch(
            "charm.DatabaseConfig.load",
            return_value=DatabaseConfig(migration_version="migration_version_0"),
        )
        return mocked.return_value

    @patch("charm.CommandLine.migrate")
    def test_when_not_leader_unit(
        self,
        mocked_cli: MagicMock,
        peer_integration: testing.PeerRelation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=False)
        state_in = testing.State(
            containers={container},
            relations=[peer_integration],
            leader=False,
        )

        with pytest.raises(
            testing.ActionFailed, match="Only the leader unit can run the schema-upgrade action"
        ):
            ctx.run(ctx.on.action(name="schema-upgrade"), state_in)

        mocked_cli.assert_not_called()
        mocked_charm_holistic_handler.assert_not_called()

    @patch("charm.CommandLine.migrate")
    def test_when_container_not_connected(
        self,
        mocked_cli: MagicMock,
        peer_integration: testing.PeerRelation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=False)
        state_in = testing.State(
            containers={container},
            relations=[peer_integration],
            leader=True,
        )

        with pytest.raises(testing.ActionFailed, match="Cannot connect to the workload container"):
            ctx.run(ctx.on.action(name="schema-upgrade"), state_in)

        mocked_cli.assert_not_called()
        mocked_charm_holistic_handler.assert_not_called()

    @patch("charm.CommandLine.migrate")
    def test_when_peer_integration_not_exists(
        self,
        mocked_cli: MagicMock,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container}, leader=True)

        with pytest.raises(testing.ActionFailed, match="Peer integration is not ready"):
            ctx.run(ctx.on.action(name="schema-upgrade"), state_in)

        mocked_cli.assert_not_called()
        mocked_charm_holistic_handler.assert_not_called()

    @patch("charm.CommandLine.migrate", side_effect=MigrationError)
    def test_when_commandline_failed(
        self,
        mocked_cli: MagicMock,
        mocked_database_config: DatabaseConfig,
        peer_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[peer_integration],
            leader=True,
        )

        with pytest.raises(testing.ActionFailed, match="Database migration failed"):
            ctx.run(ctx.on.action(name="schema-upgrade"), state_in)

        mocked_cli.assert_called_once_with(mocked_database_config.dsn, timeout=120)
        mocked_charm_holistic_handler.assert_not_called()

    @patch("charm.CommandLine.migrate")
    def test_when_action_succeeds(
        self,
        mocked_cli: MagicMock,
        mocked_database_config: DatabaseConfig,
        peer_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[peer_integration],
            leader=True,
        )

        ctx.run(ctx.on.action(name="schema-upgrade"), state_in)

        assert "Successfully migrated the database" in ctx.action_logs
        assert "Successfully updated migration version" in ctx.action_logs
        mocked_cli.assert_called_once_with(mocked_database_config.dsn, timeout=120)
        mocked_charm_holistic_handler.assert_called_once()
