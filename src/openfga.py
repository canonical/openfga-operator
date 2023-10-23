# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class for managing openfga."""
import logging
import re
from typing import Dict, List, Optional, Tuple

from ops.model import Container

logger = logging.getLogger(__name__)


class OpenFGA:
    """Helper object for managing openfga."""

    def __init__(self, openfga_http_url: str, container: Container):
        self.openfga_http_url = openfga_http_url
        self.container = container

    def run_migration(self, dsn: str, timeout: float = 60) -> Optional[str]:
        """Run hydra migrations."""
        cmd = [
            "openfga",
            "migrate",
            "--datastore-engine",
            "postgres",
            "--datastore-uri",
            dsn,
        ]

        return self._run_cmd(cmd, timeout=timeout)[0]

    def get_version(self) -> str:
        """Get the version of the openfga binary."""
        cmd = ["openfga", "version"]

        _, stderr = self._run_cmd(cmd)

        # Output has the format:
        # {datetime} OpenFGA version `{version}` build from `{hash}` on `{timestamp}`
        out_re = r"OpenFGA version `(.+)` build from `(.+)` on `(.+)`"
        versions = re.findall(out_re, stderr)[0]
        return versions[0]

    def _run_cmd(
        self,
        cmd: List[str],
        timeout: float = 20,
        input_: Optional[str] = None,
        environment: Optional[Dict] = None,
    ) -> Tuple[str, str]:
        logger.debug(f"Running cmd: {cmd}")
        process = self.container.exec(cmd, environment=environment, timeout=timeout)
        if input_:
            process.stdin.write(input_)
            process.stdin.close()
        output, stderr = process.wait_output()

        return (
            output.decode() if isinstance(output, bytes) else output,
            stderr.decode() if isinstance(stderr, bytes) else stderr,
        )
