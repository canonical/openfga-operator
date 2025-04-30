# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from collections import ChainMap

from ops import Container, ModelError, Unit
from ops.pebble import Layer, LayerDict

from cli import CommandLine
from constants import (
    OPENFGA_SERVER_GRPC_PORT,
    OPENFGA_SERVER_HTTP_PORT,
    WORKLOAD_CONTAINER,
    WORKLOAD_SERVICE,
)
from env_vars import DEFAULT_CONTAINER_ENV, EnvVarConvertible
from exceptions import PebbleServiceError

logger = logging.getLogger(__name__)

PEBBLE_LAYER_DICT = {
    "summary": "pebble layer",
    "description": "pebble layer for openfga",
    "services": {
        WORKLOAD_SERVICE: {
            "override": "merge",
            "summary": "entrypoint of the openfga image",
            "command": "openfga run",
            "startup": "disabled",
        }
    },
    "checks": {
        "http-check": {
            "override": "replace",
            "period": "1m",
            "http": {"url": f"http://127.0.0.1:{OPENFGA_SERVER_HTTP_PORT}/healthz"},
        },
        "grpc-check": {
            "override": "replace",
            "period": "1m",
            "level": "alive",
            "exec": {
                "command": f"grpc_health_probe -addr 127.0.0.1:{OPENFGA_SERVER_GRPC_PORT}",
            },
        },
    },
}


class WorkloadService:
    """Workload service abstraction running in a Juju unit."""

    def __init__(self, unit: Unit) -> None:
        self._version = ""

        self._unit: Unit = unit
        self._container: Container = unit.get_container(WORKLOAD_CONTAINER)
        self._cli = CommandLine(self._container)

    @property
    def version(self) -> str:
        self._version = self._cli.get_openfga_service_version() or ""
        return self._version

    @version.setter
    def version(self, version: str) -> None:
        if not version:
            return

        try:
            self._unit.set_workload_version(version)
        except Exception as e:
            logger.error("Failed to set workload version: %s", e)
            return

        self._version = version

    @property
    def is_running(self) -> bool:
        try:
            workload_service = self._container.get_service(WORKLOAD_SERVICE)
        except ModelError:
            return False

        return workload_service.is_running()


class PebbleService:
    """Pebble service abstraction running in a Juju unit."""

    def __init__(self, unit: Unit) -> None:
        self._unit = unit
        self._container = unit.get_container(WORKLOAD_SERVICE)
        self._layer_dict: LayerDict = PEBBLE_LAYER_DICT

    def plan(self, layer: Layer) -> None:
        self._container.add_layer(WORKLOAD_SERVICE, layer, combine=True)

        try:
            self._container.restart(WORKLOAD_CONTAINER)
        except Exception as e:
            raise PebbleServiceError(f"Pebble failed to restart the workload service. Error: {e}")

    def render_pebble_layer(self, *env_var_sources: EnvVarConvertible) -> Layer:
        updated_env_vars = ChainMap(*(source.to_env_vars() for source in env_var_sources))  # type: ignore
        env_vars = {
            **DEFAULT_CONTAINER_ENV,
            **updated_env_vars,
        }
        self._layer_dict["services"][WORKLOAD_SERVICE]["environment"] = env_vars

        return Layer(self._layer_dict)
