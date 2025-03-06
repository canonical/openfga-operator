# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import subprocess
from contextlib import suppress
from typing import Optional

from charms.tls_certificates_interface.v4.tls_certificates import (
    CertificateRequestAttributes,
    Mode,
    ProviderCertificate,
    TLSCertificatesRequiresV4,
)
from ops import CharmBase
from ops.pebble import PathError
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_fixed

from constants import (
    CERTIFICATE_FILE,
    CERTIFICATES_INTEGRATION_NAME,
    SERVER_CA_CERT,
    SERVER_CERT,
    SERVER_KEY,
)
from exceptions import CertificatesError

logger = logging.getLogger(__name__)


class CertificatesIntegration:
    def __init__(self, charm: CharmBase) -> None:
        self._charm = charm
        self._container = charm._container

        k8s_svc_host = f"{charm.app.name}.{charm.model.name}.svc.cluster.local"
        self.csr_attributes = CertificateRequestAttributes(
            common_name=k8s_svc_host,
            sans_dns=frozenset((k8s_svc_host, "localhost")),
            sans_ip=frozenset(("0.0.0.0",)),  # https://github.com/openfga/openfga/issues/2290
        )
        self.cert_requirer = TLSCertificatesRequiresV4(
            charm,
            relationship_name=CERTIFICATES_INTEGRATION_NAME,
            certificate_requests=[self.csr_attributes],
            mode=Mode.UNIT,
        )

    @property
    def tls_enabled(self) -> bool:
        return (
            self._container.exists(SERVER_KEY)
            and self._container.exists(SERVER_CERT)
            and self._container.exists(CERTIFICATE_FILE)
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

    def update_certificates(self) -> None:
        if not self._charm.model.get_relation(CERTIFICATES_INTEGRATION_NAME):
            logger.info("The certificates integration is not ready.")
            self._remove_certificates()
            return

        if not self.certs_ready():
            logger.info("The certificates data is not ready.")
            self._remove_certificates()
            return

        self._prepare_certificates()
        self._push_certificates()

    def certs_ready(self) -> bool:
        certs, private_key = self.cert_requirer.get_assigned_certificate(self.csr_attributes)
        return all((certs, private_key))

    def _prepare_certificates(self) -> None:
        SERVER_CA_CERT.write_text(self._ca_cert)  # type: ignore[arg-type]
        SERVER_KEY.write_text(self._server_key)  # type: ignore[arg-type]
        SERVER_CERT.write_text(self._server_cert)  # type: ignore[arg-type]

        try:
            for attempt in Retrying(
                wait=wait_fixed(3),
                stop=stop_after_attempt(3),
                retry=retry_if_exception_type(subprocess.CalledProcessError),
                reraise=True,
            ):
                with attempt:
                    subprocess.run(
                        ["update-ca-certificates", "--fresh"],
                        check=True,
                        text=True,
                        capture_output=True,
                    )
        except subprocess.CalledProcessError as e:
            logger.error("Failed to update the TLS certificates: %s", e.stderr)
            raise CertificatesError("Update the TLS certificates failed.")

    def _push_certificates(self) -> None:
        self._container.push(CERTIFICATE_FILE, CERTIFICATE_FILE.read_text(), make_dirs=True)
        self._container.push(SERVER_CA_CERT, self._ca_cert, make_dirs=True)
        self._container.push(SERVER_KEY, self._server_key, make_dirs=True)
        self._container.push(SERVER_CERT, self._server_cert, make_dirs=True)

    def _remove_certificates(self) -> None:
        for file in (CERTIFICATE_FILE, SERVER_CA_CERT, SERVER_KEY, SERVER_CERT):
            with suppress(PathError):
                self._container.remove_path(file)
