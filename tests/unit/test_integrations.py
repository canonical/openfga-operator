# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, create_autospec

import pytest
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer

from constants import OPENFGA_SERVER_HTTP_PORT, POSTGRESQL_DSN_TEMPLATE
from integrations import (
    DatabaseConfig,
    GRpcIngressIntegration,
    HttpIngressIntegration,
    PeerData,
    TracingData,
)


class TestPeerData:
    @pytest.fixture
    def mocked_app(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mocked_model(self, mocked_app: MagicMock) -> MagicMock:
        model = MagicMock()
        model.app = mocked_app
        return model

    @pytest.fixture
    def peer_data(self, mocked_model: MagicMock) -> PeerData:
        return PeerData(mocked_model)

    @pytest.fixture
    def mocked_peer_integration_data(self, mocked_app: MagicMock, mocked_model: MagicMock) -> dict:
        peer_integration = MagicMock()
        peer_integration.data = {mocked_app: {}}
        mocked_model.get_relation.return_value = peer_integration
        return peer_integration.data[mocked_app]

    def test_get_with_existing_key(
        self, mocked_peer_integration_data: dict, peer_data: PeerData
    ) -> None:
        mocked_peer_integration_data["key"] = '"val"'
        assert peer_data["key"] == "val"

    def test_get_with_missing_key(
        self, mocked_peer_integration_data: dict, peer_data: PeerData
    ) -> None:
        assert not peer_data["missing"]

    def test_get_without_peer_integration(
        self, mocked_model: MagicMock, peer_data: PeerData
    ) -> None:
        mocked_model.get_relation.return_value = None
        assert not peer_data["key"]

    def test_set(self, mocked_peer_integration_data: dict, peer_data: PeerData) -> None:
        peer_data["key"] = "val"
        assert mocked_peer_integration_data["key"] == '"val"'

    def test_set_without_integration(
        self,
        mocked_model: MagicMock,
        mocked_peer_integration_data: dict,
        peer_data: PeerData,
    ) -> None:
        mocked_model.get_relation.return_value = None
        peer_data["key"] = "val"

        assert not mocked_peer_integration_data

    def test_pop_with_existing_key(
        self, mocked_peer_integration_data: dict, peer_data: PeerData
    ) -> None:
        mocked_peer_integration_data["key"] = '"val"'

        actual = peer_data.pop("key")
        assert actual == "val"
        assert "key" not in mocked_peer_integration_data

    def test_pop_with_missing_key(
        self, mocked_peer_integration_data: dict, peer_data: PeerData
    ) -> None:
        assert not peer_data.pop("key")

    def test_pop_without_integration(
        self,
        mocked_model: MagicMock,
        mocked_peer_integration_data: dict,
        peer_data: PeerData,
    ) -> None:
        mocked_model.get_relation.return_value = None
        assert not peer_data.pop("key")

    def test_keys(self, mocked_peer_integration_data: dict, peer_data: PeerData) -> None:
        mocked_peer_integration_data.update({"x": "1", "y": "2"})
        assert list(peer_data.keys()) == ["x", "y"]

    def test_keys_without_integration(self, mocked_model: MagicMock, peer_data: PeerData) -> None:
        mocked_model.get_relation.return_value = None
        assert not peer_data.keys()


class TestDatabaseConfig:
    @pytest.fixture
    def database_config(self) -> DatabaseConfig:
        return DatabaseConfig(
            username="username",
            password="password",
            endpoint="endpoint",
            database="database",
            migration_version="migration_version",
        )

    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(DatabaseRequires)

    def test_dsn(self, database_config: DatabaseConfig) -> None:
        expected = POSTGRESQL_DSN_TEMPLATE.substitute(
            username="username",
            password="password",
            endpoint="endpoint",
            database="database",
        )

        actual = database_config.dsn
        assert actual == expected

    def test_to_service_configs(self, database_config: DatabaseConfig) -> None:
        env_vars = database_config.to_env_vars()
        assert env_vars["OPENFGA_DATASTORE_URI"] == database_config.dsn

    def test_load_with_integration(self, mocked_requirer: MagicMock) -> None:
        integration_id = 1
        mocked_requirer.relations = [MagicMock(id=integration_id)]
        mocked_requirer.database = "database"
        mocked_requirer.fetch_relation_data.return_value = {
            integration_id: {
                "endpoints": "endpoint",
                "username": "username",
                "password": "password",
            }
        }

        actual = DatabaseConfig.load(mocked_requirer)
        assert actual == DatabaseConfig(
            username="username",
            password="password",
            endpoint="endpoint",
            database="database",
            migration_version="migration_version_1",
        )

    def test_load_without_integration(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.database = "database"
        mocked_requirer.relations = []

        actual = DatabaseConfig.load(mocked_requirer)
        assert actual == DatabaseConfig()


class TestTracingData:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(TracingEndpointRequirer)

    @pytest.mark.parametrize(
        "data, expected",
        [
            (TracingData(is_ready=False), {}),
            (
                TracingData(is_ready=True, grpc_endpoint="grpc_endpoint"),
                {
                    "OPENFGA_TRACE_ENABLED": True,
                    "OPENFGA_TRACE_OTLP_ENDPOINT": "grpc_endpoint",
                    "OPENFGA_TRACE_SAMPLE_RATIO": "0.3",
                },
            ),
        ],
    )
    def test_to_env_vars(self, data: TracingData, expected: dict) -> None:
        actual = data.to_env_vars()
        assert actual == expected

    def test_load_with_integration_ready(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.is_ready.return_value = True
        mocked_requirer.get_endpoint.return_value = "http://grpc_endpoint"

        actual = TracingData.load(mocked_requirer)
        assert actual == TracingData(is_ready=True, grpc_endpoint="grpc_endpoint")

    def test_load_without_integration_ready(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.is_ready.return_value = False

        actual = TracingData.load(mocked_requirer)
        assert actual == TracingData()


class TestHttpIngressIntegration:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mocked_charm(self) -> MagicMock:
        charm = MagicMock()
        charm.model.name = "test"
        charm.app.name = "openfga"
        charm._certs_integration.uri_scheme = "https"
        return charm

    def test_url_when_ingress_ready(
        self, mocked_requirer: MagicMock, mocked_charm: MagicMock
    ) -> None:
        mocked_requirer.is_ready.return_value = True
        mocked_requirer.url = "https://http.test.com"

        ingress = HttpIngressIntegration(mocked_charm)
        ingress.ingress_requirer = mocked_requirer

        assert ingress.url == "https://http.test.com"

    def test_url_when_ingress_not_ready(
        self, mocked_requirer: MagicMock, mocked_charm: MagicMock
    ) -> None:
        mocked_requirer.is_ready.return_value = False

        ingress = HttpIngressIntegration(mocked_charm)
        ingress.ingress_requirer = mocked_requirer

        assert (
            ingress.url
            == f"https://{mocked_charm.app.name}.{mocked_charm.model.name}.svc.cluster.local:{OPENFGA_SERVER_HTTP_PORT}"
        )


class TestGRpcIngressIntegration:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mocked_charm(self) -> MagicMock:
        charm = MagicMock()
        charm.model.name = "test"
        charm.app.name = "openfga"
        return charm

    def test_url_when_ingress_ready(
        self, mocked_requirer: MagicMock, mocked_charm: MagicMock
    ) -> None:
        mocked_requirer.is_ready.return_value = True
        mocked_requirer.url = "https://grpc.test.com"

        ingress = GRpcIngressIntegration(mocked_charm)
        ingress.ingress_requirer = mocked_requirer

        assert ingress.url == "https://grpc.test.com"

    def test_url_when_ingress_not_ready(
        self, mocked_requirer: MagicMock, mocked_charm: MagicMock
    ) -> None:
        mocked_requirer.is_ready.return_value = False

        ingress = GRpcIngressIntegration(mocked_charm)
        ingress.ingress_requirer = mocked_requirer

        assert (
            ingress.url
            == f"{mocked_charm.app.name}.{mocked_charm.model.name}.svc.cluster.local:{OPENFGA_SERVER_HTTP_PORT}"
        )
