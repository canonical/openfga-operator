# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import re
from typing import Optional

from ops import Container
from ops.pebble import Error, ExecError

from exceptions import MigrationError

logger = logging.getLogger(__name__)

VERSION_REGEX = re.compile(r"(?P<version>v\d+\.\d+\.\d+)")


class CommandLine:
    def __init__(self, container: Container):
        self.container = container

    def get_openfga_service_version(self) -> Optional[str]:
        """Get OpenFGA application version.

        Version command output format:
        # {datetime} OpenFGA version `{version}` build from `{hash}` on `{timestamp}`
        """
        cmd = ["openfga", "version"]

        try:
            _, stderr = self._run_cmd(cmd)
        except Error as err:
            logger.error("Failed to fetch the OpenFGA version: %s", err)
            return None

        matched = VERSION_REGEX.search(stderr)
        return matched.group("version") if matched else None

    def migrate(self, dsn: str, timeout: float = 60) -> None:
        """Apply OpenFGA database migration.

        More information: https://openfga.dev/docs/getting-started/setup-openfga/configure-openfga#configuring-data-storage
        """
        cmd = [
            "openfga",
            "migrate",
            "--datastore-engine",
            "postgres",
            "--datastore-uri",
            dsn,
        ]

        try:
            self._run_cmd(cmd, timeout=timeout)
        except Error as err:
            logger.error("Failed to migrate OpenFGA: %s", err)
            raise MigrationError from err

    def _run_cmd(
        self,
        cmd: list[str],
        timeout: float = 20,
        environment: Optional[dict] = None,
    ) -> tuple[str, str]:
        logger.debug(f"Running command: {cmd}")
        process = self.container.exec(cmd, environment=environment, timeout=timeout)
        try:
            stdout, stderr = process.wait_output()
        except ExecError as err:
            logger.error("Exited with code: %d. Error: %s", err.exit_code, err.stderr)
            raise

        return (
            stdout.decode() if isinstance(stdout, bytes) else stdout,
            stderr.decode() if isinstance(stderr, bytes) else stderr,
        )
