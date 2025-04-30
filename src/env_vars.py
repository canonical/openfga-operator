# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Mapping, Protocol, TypeAlias, Union

EnvVars: TypeAlias = Mapping[str, Union[str, bool]]

DEFAULT_CONTAINER_ENV = {
    "OPENFGA_PLAYGROUND_ENABLED": False,
    "OPENFGA_DATASTORE_ENGINE": "postgres",
    "OPENFGA_METRICS_ENABLE_RPC_HISTOGRAMS": "true",
    "OPENFGA_METRICS_ENABLED": "true",
    "OPENFGA_DATASTORE_METRICS_ENABLED": "true",
    "OPENFGA_HTTP_TLS_ENABLED": "false",
    "OPENFGA_GRPC_TLS_ENABLED": "false",
    "OPENFGA_LOG_FORMAT": "json",
}


class EnvVarConvertible(Protocol):
    """An interface enforcing the contribution to workload service environment variables."""

    def to_env_vars(self) -> EnvVars:
        pass
