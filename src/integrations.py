# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, KeysView, Optional, Type, TypeAlias, Union
from urllib.parse import urlparse

from charms.certificate_transfer_interface.v0.certificate_transfer import (
    CertificateTransferProvides,
)
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from charms.tls_certificates_interface.v4.tls_certificates import (
    CertificateRequestAttributes,
    Mode,
    ProviderCertificate,
    TLSCertificatesRequiresV4,
)
from charms.traefik_k8s.v2.ingress import IngressPerAppRequirer
from ops import CharmBase, Model
from ops.pebble import PathError
from typing_extensions import Self

from constants import (
    CA_BUNDLE_FILE,
    CERTIFICATES_INTEGRATION_NAME,
    CERTIFICATES_TRANSFER_INTEGRATION_NAME,
    GRPC_INGRESS_INTEGRATION_NAME,
    HTTP_INGRESS_INTEGRATION_NAME,
    OPENFGA_SERVER_GRPC_PORT,
    OPENFGA_SERVER_HTTP_PORT,
    PEER_INTEGRATION_NAME,
    POSTGRESQL_DSN_TEMPLATE,
    SERVER_CERT,
    SERVER_KEY,
)
from env_vars import EnvVars

logger = logging.getLogger(__name__)

JsonSerializable: TypeAlias = Union[dict[str, Any], list[Any], int, str, float, bool, Type[None]]


class PeerData:
    def __init__(self, model: Model) -> None:
        self._model = model
        self._app = model.app

    def __getitem__(self, key: str) -> JsonSerializable:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return {}

        value = peers.data[self._app].get(key)
        return json.loads(value) if value else {}

    def __setitem__(self, key: str, value: Any) -> None:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return

        peers.data[self._app][key] = json.dumps(value)

    def pop(self, key: str) -> JsonSerializable:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return {}

        data = peers.data[self._app].pop(key, None)
        return json.loads(data) if data else {}

    def keys(self) -> KeysView[str]:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return KeysView({})

        return peers.data[self._app].keys()


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """The data source from the database integration."""

    endpoint: str = ""
    database: str = ""
    username: str = ""
    password: str = ""
    migration_version: str = ""

    @property
    def dsn(self) -> str:
        return POSTGRESQL_DSN_TEMPLATE.substitute(
            username=self.username,
            password=self.password,
            endpoint=self.endpoint,
            database=self.database,
        )

    def to_env_vars(self) -> EnvVars:
        return {
            "OPENFGA_DATASTORE_URI": self.dsn,
        }

    @classmethod
    def load(cls, requirer: DatabaseRequires) -> Self:
        if not (database_integrations := requirer.relations):
            return cls()

        integration_id = database_integrations[0].id
        integration_data: dict[str, str] = requirer.fetch_relation_data()[integration_id]

        return cls(
            endpoint=integration_data.get("endpoints", "").split(",")[0],
            database=requirer.database,
            username=integration_data.get("username", ""),
            password=integration_data.get("password", ""),
            migration_version=f"migration_version_{integration_id}",
        )


@dataclass
class CertificateData:
    ca_cert: Optional[str] = None
    ca_chain: Optional[list[str]] = None
    cert: Optional[str] = None


class CertificatesIntegration:
    def __init__(self, charm: CharmBase) -> None:
        self._charm = charm
        self._container = charm._container

        k8s_svc_host = f"{charm.app.name}.{charm.model.name}.svc.cluster.local"
        self.csr_attributes = CertificateRequestAttributes(
            common_name=k8s_svc_host,
            sans_dns=frozenset((k8s_svc_host,)),
            sans_ip=frozenset((
                "127.0.0.1",
                "0.0.0.0",
            )),  # https://github.com/openfga/openfga/issues/2290
        )
        self.cert_requirer = TLSCertificatesRequiresV4(
            charm,
            relationship_name=CERTIFICATES_INTEGRATION_NAME,
            certificate_requests=[self.csr_attributes],
            mode=Mode.UNIT,
        )

    def to_env_vars(self) -> EnvVars:
        if not self.tls_enabled:
            return {}

        return {
            "OPENFGA_HTTP_TLS_ENABLED": "true",
            "OPENFGA_HTTP_TLS_CERT": str(SERVER_CERT),
            "OPENFGA_HTTP_TLS_KEY": str(SERVER_KEY),
            "OPENFGA_GRPC_TLS_ENABLED": "true",
            "OPENFGA_GRPC_TLS_CERT": str(SERVER_CERT),
            "OPENFGA_GRPC_TLS_KEY": str(SERVER_KEY),
        }

    @property
    def tls_enabled(self) -> bool:
        if not self._container.can_connect():
            return False

        return (
            self._container.exists(SERVER_KEY)
            and self._container.exists(SERVER_CERT)
            and self._container.exists(CA_BUNDLE_FILE)
        )

    @property
    def uri_scheme(self) -> str:
        return "https" if self.tls_enabled else "http"

    @property
    def _ca_cert(self) -> Optional[str]:
        return str(self._certs.ca) if self._certs else None

    @property
    def _server_key(self) -> Optional[str]:
        private_key = self.cert_requirer.private_key
        return str(private_key) if private_key else None

    @property
    def _server_cert(self) -> Optional[str]:
        return str(self._certs.certificate) if self._certs else None

    @property
    def _ca_chain(self) -> Optional[list[str]]:
        return [str(chain) for chain in self._certs.chain] if self._certs else None

    @property
    def _certs(self) -> Optional[ProviderCertificate]:
        cert, *_ = self.cert_requirer.get_assigned_certificate(self.csr_attributes)
        return cert

    @property
    def cert_data(self) -> CertificateData:
        return CertificateData(
            ca_cert=self._ca_cert,
            ca_chain=self._ca_chain,
            cert=self._server_cert,
        )

    def update_certificates(self) -> None:
        if not self._charm.model.get_relation(CERTIFICATES_INTEGRATION_NAME):
            logger.info("The certificates integration is not ready.")
            self._remove_certificates()
            return

        if not self._certs_ready():
            logger.info("The certificates data is not ready.")
            self._remove_certificates()
            return

        self._push_certificates()

    def _certs_ready(self) -> bool:
        certs, private_key = self.cert_requirer.get_assigned_certificate(self.csr_attributes)
        return all((certs, private_key))

    def _push_certificates(self) -> None:
        self._container.push(CA_BUNDLE_FILE, self._ca_cert, make_dirs=True)
        self._container.push(SERVER_KEY, self._server_key, make_dirs=True)
        self._container.push(SERVER_CERT, self._server_cert, make_dirs=True)

    def _remove_certificates(self) -> None:
        for file in (CA_BUNDLE_FILE, SERVER_KEY, SERVER_CERT):
            with suppress(PathError):
                self._container.remove_path(file)


class CertificatesTransferIntegration:
    def __init__(self, charm: CharmBase):
        self._charm = charm
        self._certs_transfer_provider = CertificateTransferProvides(
            charm, relationship_name=CERTIFICATES_TRANSFER_INTEGRATION_NAME
        )

    def transfer_certificates(
        self, /, data: CertificateData, relation_id: Optional[int] = None
    ) -> None:
        if not (
            relations := self._charm.model.relations.get(CERTIFICATES_TRANSFER_INTEGRATION_NAME)
        ):
            return

        if relation_id is not None:
            relations = [relation for relation in relations if relation.id == relation_id]

        ca_cert, ca_chain, certificate = data.ca_cert, data.ca_chain, data.cert
        if not all((ca_cert, ca_chain, certificate)):
            for relation in relations:
                self._certs_transfer_provider.remove_certificate(relation_id=relation.id)
            return

        for relation in relations:
            self._certs_transfer_provider.set_certificate(
                ca=data.ca_cert,  # type: ignore[arg-type]
                chain=data.ca_chain,  # type: ignore[arg-type]
                certificate=data.cert,  # type: ignore[arg-type]
                relation_id=relation.id,
            )


@dataclass(frozen=True, slots=True)
class TracingData:
    """The data source from the tracing integration."""

    is_ready: bool = False
    grpc_endpoint: str = ""

    def to_env_vars(self) -> EnvVars:
        if not self.is_ready:
            return {}

        return {
            "OPENFGA_TRACE_ENABLED": True,
            "OPENFGA_TRACE_OTLP_ENDPOINT": self.grpc_endpoint,
            "OPENFGA_TRACE_SAMPLE_RATIO": "0.3",
        }

    @classmethod
    def load(cls, requirer: TracingEndpointRequirer) -> "TracingData":
        if not (is_ready := requirer.is_ready()):
            return cls()

        grpc_endpoint = urlparse(requirer.get_endpoint("otlp_grpc"))

        return cls(
            is_ready=is_ready,
            grpc_endpoint=grpc_endpoint.geturl().replace(f"{grpc_endpoint.scheme}://", "", 1),  # type: ignore
        )


class HttpIngressIntegration:
    def __init__(self, charm: CharmBase) -> None:
        self._charm = charm
        self._uri_scheme = charm._certs_integration.uri_scheme
        self.ingress_requirer = IngressPerAppRequirer(
            self._charm,
            relation_name=HTTP_INGRESS_INTEGRATION_NAME,
            port=OPENFGA_SERVER_HTTP_PORT,
            strip_prefix=True,
        )

    @property
    def url(self) -> str:
        k8s_svc = (
            f"{self._uri_scheme}://{self._charm.app.name}.{self._charm.model.name}.svc.cluster.local"
            f":{OPENFGA_SERVER_HTTP_PORT}"
        )
        return self.ingress_requirer.url if self.ingress_requirer.is_ready() else k8s_svc


class GRpcIngressIntegration:
    def __init__(self, charm: CharmBase) -> None:
        self._charm = charm
        self.ingress_requirer = IngressPerAppRequirer(
            self._charm,
            relation_name=GRPC_INGRESS_INTEGRATION_NAME,
            port=OPENFGA_SERVER_GRPC_PORT,
            strip_prefix=True,
            scheme="h2c",
        )

    @property
    def url(self) -> str:
        k8s_svc = f"{self._charm.app.name}.{self._charm.model.name}.svc.cluster.local:{OPENFGA_SERVER_HTTP_PORT}"
        return self.ingress_requirer.url if self.ingress_requirer.is_ready() else k8s_svc
