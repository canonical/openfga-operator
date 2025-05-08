# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from ops import testing

from charm import OpenFGAOperatorCharm
from constants import (
    PEER_INTEGRATION_NAME,
    PRESHARED_TOKEN_SECRET_KEY,
    PRESHARED_TOKEN_SECRET_LABEL,
    WORKLOAD_CONTAINER,
)


class TestStartEvent:
    def test_when_event_emitted(self, mocked_charm_holistic_handler: MagicMock) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        ctx.run(ctx.on.start(), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestConfigChangeEvent:
    def test_when_event_emitted(self, mocked_charm_holistic_handler: MagicMock) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        ctx.run(ctx.on.config_changed(), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestPebbleReadyEvent:
    def test_when_container_not_connected(
        self,
        mocked_workload_service: MagicMock,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=False)
        state_in = testing.State(containers={container})

        state_out = ctx.run(ctx.on.pebble_ready(container), state_in)

        assert isinstance(state_out.unit_status, testing.WaitingStatus)
        mocked_workload_service.open_ports.assert_not_called()
        mocked_charm_holistic_handler.assert_not_called()

    def test_when_event_emitted(
        self,
        mocked_workload_service_version: MagicMock,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        ctx.run(ctx.on.pebble_ready(container), state_in)

        mocked_charm_holistic_handler.assert_called_once()
        assert mocked_workload_service_version.call_count > 1, (
            "workload service version should be set"
        )
        assert mocked_workload_service_version.call_args[0] == (
            mocked_workload_service_version.return_value,
        )


class TestLeaderElectedEvent:
    @pytest.fixture
    def mocked_secret(self) -> MagicMock:
        return MagicMock()

    @patch("charm.Secrets", autospec=True)
    def test_when_secrets_ready(
        self, mocked_secrets_cls: MagicMock, mocked_secret: MagicMock
    ) -> None:
        mocked_secret.is_ready = True
        mocked_secrets_cls.return_value = mocked_secret

        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container}, leader=True)

        ctx.run(ctx.on.leader_elected(), state_in)

        mocked_secret.__setitem__.assert_not_called()

    @patch("charm.Secrets", autospec=True)
    def test_when_event_emitted(
        self, mocked_secrets_cls: MagicMock, mocked_secret: MagicMock
    ) -> None:
        mocked_secret.is_ready = False
        mocked_secrets_cls.return_value = mocked_secret

        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container}, leader=True)

        ctx.run(ctx.on.leader_elected(), state_in)

        mocked_secret.__setitem__.assert_called_once()


class TestDatabaseIntegrationBrokenEvent:
    def test_when_event_emitted(
        self,
        database_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container}, relations=[database_integration])

        ctx.run(ctx.on.relation_broken(database_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestDatabaseCreatedEvent:
    def test_when_container_not_connected(
        self,
        database_integration: testing.Relation,
        peer_integration: testing.PeerRelation,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=False)
        state_in = testing.State(
            containers={container},
            relations=[database_integration, peer_integration],
            leader=True,
        )

        state_out = ctx.run(ctx.on.relation_changed(database_integration), state_in)

        assert state_out.unit_status == testing.WaitingStatus("Container is not connected yet")

    def test_when_peer_integration_not_exists(
        self,
        database_integration: testing.Relation,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[database_integration],
            leader=True,
        )

        state_out = ctx.run(ctx.on.relation_changed(database_integration), state_in)

        assert state_out.unit_status == testing.WaitingStatus(
            f"Missing integration {PEER_INTEGRATION_NAME}"
        )

    @patch("charm.CommandLine.migrate")
    def test_when_migration_not_needed(
        self,
        mocked_cli_migrate: MagicMock,
        database_integration: testing.Relation,
        peer_integration: testing.PeerRelation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[database_integration, peer_integration],
            leader=True,
        )

        with patch(
            "charm.OpenFGAOperatorCharm.migration_needed",
            new_callable=PropertyMock,
            return_value=False,
        ):
            ctx.run(ctx.on.relation_changed(database_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()
        mocked_cli_migrate.assert_not_called()

    def test_when_not_leader_unit(
        self,
        database_integration: testing.Relation,
        peer_integration: testing.PeerRelation,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[database_integration, peer_integration],
            leader=False,
        )

        state_out = ctx.run(ctx.on.relation_changed(database_integration), state_in)

        assert state_out.unit_status == testing.WaitingStatus(
            "Waiting for leader unit to run the migration"
        )

    @patch("charm.CommandLine.migrate")
    def test_when_leader_unit(
        self,
        mocked_cli_migrate: MagicMock,
        database_integration: testing.Relation,
        peer_integration: testing.PeerRelation,
        mocked_migration_needed: MagicMock,
        mocked_charm_holistic_handler: MagicMock,
        mocked_workload_service_version: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[database_integration, peer_integration],
            leader=True,
        )

        state_out = ctx.run(ctx.on.relation_changed(database_integration), state_in)

        mocked_cli_migrate.assert_called_once()
        mocked_charm_holistic_handler.assert_called_once()

        assert state_out.get_relations("peer")[0].local_app_data[
            f"migration_version_{database_integration.id}"
        ] == json.dumps(mocked_workload_service_version.return_value)


class TestHttpIngressReadyEvent:
    def test_when_event_emitted(
        self,
        http_ingress_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[http_ingress_integration],
        )

        ctx.run(ctx.on.relation_joined(http_ingress_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestHttpIngressRevokedEvent:
    def test_when_event_emitted(
        self,
        http_ingress_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[http_ingress_integration],
        )

        ctx.run(ctx.on.relation_broken(http_ingress_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestGRpcIngressReadyEvent:
    def test_when_event_emitted(
        self,
        grpc_ingress_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[grpc_ingress_integration],
        )

        ctx.run(ctx.on.relation_joined(grpc_ingress_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestGRpcIngressRevokedEvent:
    def test_when_event_emitted(
        self,
        grpc_ingress_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[grpc_ingress_integration],
        )

        ctx.run(ctx.on.relation_broken(grpc_ingress_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestOpenFGAStoreRequestEvent:
    @pytest.fixture
    def mocked_secret(self) -> MagicMock:
        return MagicMock()

    @patch("charm.Secrets", autospec=True)
    def test_when_secrets_not_ready(
        self,
        mocked_secrets_cls: MagicMock,
        mocked_secret: MagicMock,
        mocked_workload_service_running: MagicMock,
        openfga_integration: testing.Relation,
    ) -> None:
        mocked_secret.is_ready = False
        mocked_secrets_cls.return_value = mocked_secret

        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[openfga_integration],
            leader=True,
        )

        with (
            patch("charm.OpenFGAProvider.update_relation_info") as mocked_update_relation_info,
            patch(
                "charm.OpenFGAStore.create", return_value="store_id"
            ) as mocked_openfga_store_create,
        ):
            ctx.run(ctx.on.relation_changed(openfga_integration), state_in)

        mocked_openfga_store_create.assert_not_called()
        mocked_update_relation_info.assert_not_called()

    @patch("charm.Secrets", autospec=True)
    def test_when_workload_service_not_running(
        self,
        mocked_secrets_cls: MagicMock,
        mocked_secret: MagicMock,
        openfga_integration: testing.Relation,
    ) -> None:
        mocked_secret.is_ready = True
        mocked_secrets_cls.return_value = mocked_secret

        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[openfga_integration],
            leader=True,
        )

        with (
            patch(
                "charm.WorkloadService.is_running", new_callable=PropertyMock, return_value=False
            ),
            patch("charm.OpenFGAProvider.update_relation_info") as mocked_update_relation_info,
            patch(
                "charm.OpenFGAStore.create", return_value="store_id"
            ) as mocked_openfga_store_create,
        ):
            ctx.run(ctx.on.relation_changed(openfga_integration), state_in)

        mocked_openfga_store_create.assert_not_called()
        mocked_update_relation_info.assert_not_called()

    @patch("charm.Secrets", autospec=True)
    def test_when_event_emitted(
        self,
        mocked_secrets_cls: MagicMock,
        mocked_secret: MagicMock,
        # mocked_openfga_store: MagicMock,
        openfga_integration: testing.Relation,
        mocked_workload_service_running: MagicMock,
    ) -> None:
        mocked_secret.is_ready = True
        mocked_secrets_cls.return_value = mocked_secret
        secret = testing.Secret(
            tracked_content={PRESHARED_TOKEN_SECRET_KEY: "api_token"},
            label=PRESHARED_TOKEN_SECRET_LABEL,
        )

        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[openfga_integration],
            secrets=[secret],
            leader=True,
        )

        with (
            patch("charm.OpenFGAProvider.update_relation_info") as mocked_update_relation_info,
            patch(
                "charm.OpenFGAStore.create", return_value="store_id"
            ) as mocked_openfga_store_create,
        ):
            ctx.run(ctx.on.relation_changed(openfga_integration), state_in)

        mocked_openfga_store_create.assert_called_once()
        mocked_update_relation_info.assert_called_once()


class TestCertificatesTransferRelationJoinedEvent:
    def test_when_tls_not_enabled(
        self,
        certificates_transfer_integration: testing.Relation,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[certificates_transfer_integration],
        )

        with (
            patch(
                "charm.CertificatesIntegration.tls_enabled",
                new_callable=PropertyMock,
                return_value=False,
            ),
            patch(
                "charm.CertificatesTransferIntegration.transfer_certificates"
            ) as mocked_transfer_certificates,
        ):
            ctx.run(ctx.on.relation_joined(certificates_transfer_integration), state_in)

        mocked_transfer_certificates.assert_not_called()

    def test_when_tls_enabled(
        self,
        certificates_transfer_integration: testing.Relation,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[certificates_transfer_integration],
        )

        with (
            patch(
                "charm.CertificatesIntegration.tls_enabled",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch(
                "charm.CertificatesTransferIntegration.transfer_certificates"
            ) as mocked_transfer_certificates,
        ):
            ctx.run(ctx.on.relation_joined(certificates_transfer_integration), state_in)

        mocked_transfer_certificates.assert_called_once()


class TestTracingEndpointChangedEvent:
    def test_when_event_emitted(
        self,
        tracing_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[tracing_integration],
        )

        ctx.run(ctx.on.relation_changed(tracing_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestTracingEndpointRemovedEvent:
    def test_when_event_emitted(
        self,
        tracing_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(OpenFGAOperatorCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[tracing_integration],
        )

        ctx.run(ctx.on.relation_broken(tracing_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()
