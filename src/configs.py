# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Any, Mapping, Protocol, TypeAlias

from ops import ConfigData

ServiceConfigs: TypeAlias = Mapping[str, Any]


class ServiceConfigSource(Protocol):
    """An interface enforcing the contribution to workload service configs."""

    def to_service_configs(self) -> ServiceConfigs:
        pass


class CharmConfig:
    """A class representing the data source of charm configurations."""

    def __init__(self, config: ConfigData) -> None:
        self._config = config

    def to_service_configs(self) -> ServiceConfigs:
        return {
            "OPENFGA_LOG_LEVEL": self._config["log_level"],
        }
