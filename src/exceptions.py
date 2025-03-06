# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.


class CharmError(Exception):
    """Base class for custom charm errors."""


class CertificatesError(CharmError):
    """Error for tls certificates related operations."""
