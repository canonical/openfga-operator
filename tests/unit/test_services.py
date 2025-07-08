# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from ops import ModelError

from constants import (
    CA_BUNDLE_FILE,
    OPENFGA_METRICS_HTTP_PORT,
    OPENFGA_SERVER_GRPC_PORT,
    OPENFGA_SERVER_HTTP_PORT,
    WORKLOAD_SERVICE,
)
from env_vars import DEFAULT_CONTAINER_ENV, EnvVarConvertible
from exceptions import PebbleServiceError
from services import PebbleService, WorkloadService


class TestWorkloadService:
    @pytest.fixture
    def workload_service(
        self, mocked_container: MagicMock, mocked_unit: MagicMock
    ) -> WorkloadService:
        return WorkloadService(mocked_unit)

    @pytest.mark.parametrize("version, expected", [("v1.0.0", "v1.0.0"), (None, "")])
    def test_get_version(
        self, workload_service: WorkloadService, version: Optional[str], expected: str
    ) -> None:
        with patch("cli.CommandLine.get_openfga_service_version", return_value=version):
            assert workload_service.version == expected

    def test_set_version(self, mocked_unit: MagicMock, workload_service: WorkloadService) -> None:
        workload_service.version = "v1.0.0"
        mocked_unit.set_workload_version.assert_called_once_with("v1.0.0")

    def test_set_empty_version(
        self, mocked_unit: MagicMock, workload_service: WorkloadService
    ) -> None:
        workload_service.version = ""
        mocked_unit.set_workload_version.assert_not_called()

    def test_set_version_with_error(
        self,
        mocked_unit: MagicMock,
        workload_service: WorkloadService,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        error_msg = "Error from unit"
        mocked_unit.set_workload_version.side_effect = Exception(error_msg)

        with caplog.at_level("ERROR"):
            workload_service.version = "v1.0.0"

        mocked_unit.set_workload_version.assert_called_once_with("v1.0.0")
        assert f"Failed to set workload version: {error_msg}" in caplog.text

    def test_is_running(
        self, mocked_container: MagicMock, workload_service: WorkloadService
    ) -> None:
        mocked_service_info = MagicMock(is_running=MagicMock(return_value=True))

        with patch.object(
            mocked_container, "get_service", return_value=mocked_service_info
        ) as get_service:
            is_running = workload_service.is_running

        assert is_running is True
        get_service.assert_called_once_with(WORKLOAD_SERVICE)

    def test_is_running_with_error(
        self, mocked_container: MagicMock, workload_service: WorkloadService
    ) -> None:
        with patch.object(mocked_container, "get_service", side_effect=ModelError):
            is_running = workload_service.is_running

        assert is_running is False

    def test_open_ports(self, mocked_unit: MagicMock, workload_service: WorkloadService) -> None:
        workload_service.open_ports()

        assert mocked_unit.open_port.call_count == 3
        mocked_unit.open_port.assert_any_call(protocol="tcp", port=OPENFGA_SERVER_HTTP_PORT)
        mocked_unit.open_port.assert_any_call(protocol="tcp", port=OPENFGA_SERVER_GRPC_PORT)
        mocked_unit.open_port.assert_any_call(protocol="tcp", port=OPENFGA_METRICS_HTTP_PORT)


class TestPebbleService:
    @pytest.fixture
    def pebble_service(self, mocked_unit: MagicMock) -> PebbleService:
        return PebbleService(mocked_unit)

    @patch("ops.pebble.Layer")
    def test_plan(
        self,
        mocked_layer: MagicMock,
        mocked_container: MagicMock,
        pebble_service: PebbleService,
    ) -> None:
        pebble_service.plan(mocked_layer)

        mocked_container.add_layer.assert_called_once_with(
            WORKLOAD_SERVICE, mocked_layer, combine=True
        )
        mocked_container.replan.assert_called_once()

    @patch("ops.pebble.Layer")
    def test_plan_failure(
        self,
        mocked_layer: MagicMock,
        mocked_container: MagicMock,
        pebble_service: PebbleService,
    ) -> None:
        with (
            patch.object(mocked_container, "replan", side_effect=Exception) as replan,
            pytest.raises(PebbleServiceError),
        ):
            pebble_service.plan(mocked_layer)

        mocked_container.add_layer.assert_called_once_with(
            WORKLOAD_SERVICE, mocked_layer, combine=True
        )
        replan.assert_called_once()

    @pytest.mark.parametrize(
        "env_sources, expected_env, expected_http_url, expected_grpc_cmd",
        [
            # Non-TLS case
            (
                [
                    {"key1": "value1"},
                    {"key2": "value2"},
                ],
                {
                    **DEFAULT_CONTAINER_ENV,
                    "key1": "value1",
                    "key2": "value2",
                },
                f"http://127.0.0.1:{OPENFGA_SERVER_HTTP_PORT}/healthz",
                f"grpc_health_probe -addr 127.0.0.1:{OPENFGA_SERVER_GRPC_PORT}",
            ),
            # TLS-enabled case
            (
                [
                    {
                        "OPENFGA_HTTP_TLS_ENABLED": "true",
                        "OPENFGA_GRPC_TLS_ENABLED": "true",
                    }
                ],
                {
                    **DEFAULT_CONTAINER_ENV,
                    "OPENFGA_HTTP_TLS_ENABLED": "true",
                    "OPENFGA_GRPC_TLS_ENABLED": "true",
                },
                f"https://127.0.0.1:{OPENFGA_SERVER_HTTP_PORT}/healthz",
                f"grpc_health_probe -addr 127.0.0.1:{OPENFGA_SERVER_GRPC_PORT} -tls -tls-ca-cert {CA_BUNDLE_FILE}",
            ),
        ],
    )
    def test_render_pebble_layer(
        self,
        pebble_service: PebbleService,
        env_sources: list[dict[str, str]],
        expected_env: dict[str, str],
        expected_http_url: str,
        expected_grpc_cmd: str,
    ) -> None:
        data_sources = []
        for env_vars in env_sources:
            data_source = MagicMock(spec=EnvVarConvertible)
            data_source.to_env_vars.return_value = env_vars
            data_sources.append(data_source)

        layer = pebble_service.render_pebble_layer(*data_sources)
        layer_dict = layer.to_dict()

        assert layer_dict["services"][WORKLOAD_SERVICE]["environment"] == expected_env
        assert layer_dict["checks"]["http-check"]["http"]["url"] == expected_http_url
        assert layer_dict["checks"]["grpc-check"]["exec"]["command"] == expected_grpc_cmd
