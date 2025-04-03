# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import Optional

from charms.certificate_transfer_interface.v0.certificate_transfer import (
    CertificateTransferProvides,
)
from charms.tls_certificates_interface.v4.tls_certificates import (
    CertificateRequestAttributes,
    Mode,
    ProviderCertificate,
    TLSCertificatesRequiresV4,
)
from ops import CharmBase
from ops.pebble import PathError

from constants import (
    CA_BUNDLE_FILE,
    CERTIFICATES_INTEGRATION_NAME,
    CERTIFICATES_TRANSFER_INTEGRATION_NAME,
    SERVER_CERT,
    SERVER_KEY,
)

logger = logging.getLogger(__name__)


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
