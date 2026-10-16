# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

import pytest
from ops import testing
from pytest_mock import MockerFixture

from charm import OpenFGAOperatorCharm
from constants import PRESHARED_TOKEN_SECRET_KEY, PRESHARED_TOKEN_SECRET_LABEL, WORKLOAD_CONTAINER
from exceptions import MigrationError
from integrations import DatabaseConfig


class TestGetTokenAction:
    @pytest.mark.parametrize("leader", [True, False])
    def test_when_secret_not_found(self, leader: bool) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=False)
        state_in = testing.State(leader=leader, containers={container})

        with pytest.raises(testing.ActionFailed, match="OpenFGA API token is not available yet"):
            ctx.run(ctx.on.action(name="get-token"), state_in)

        assert not ctx.action_results

    @pytest.mark.parametrize("leader", [True, False])
    @pytest.mark.parametrize("content", [{"other": "value"}, {PRESHARED_TOKEN_SECRET_KEY: ""}])
    def test_when_token_not_available(self, content: dict[str, str], leader: bool) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        secret = testing.Secret(
            tracked_content=content,
            label=PRESHARED_TOKEN_SECRET_LABEL,
            owner="app",
        )
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=False)
        state_in = testing.State(leader=leader, secrets={secret}, containers={container})

        with pytest.raises(testing.ActionFailed, match="OpenFGA API token is not available yet"):
            ctx.run(ctx.on.action(name="get-token"), state_in)

        assert not ctx.action_results

    @pytest.mark.parametrize("leader", [True, False])
    def test_when_action_succeeds(
        self,
        leader: bool,
        mocked_charm_holistic_handler: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        secret = testing.Secret(
            tracked_content={PRESHARED_TOKEN_SECRET_KEY: "test-preshared-token"},
            label=PRESHARED_TOKEN_SECRET_LABEL,
            owner="app",
        )
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=False)
        state_in = testing.State(leader=leader, secrets={secret}, containers={container})

        state_out = ctx.run(ctx.on.action(name="get-token"), state_in)

        assert ctx.action_results == {"token": "test-preshared-token"}
        assert not ctx.action_logs
        assert "test-preshared-token" not in caplog.text
        assert state_out.secrets == state_in.secrets
        assert state_out.unit_status == state_in.unit_status
        mocked_charm_holistic_handler.assert_not_called()


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
