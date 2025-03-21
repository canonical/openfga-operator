# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class for managing openfga."""

import logging
import re
from typing import Dict, List, Optional, Tuple

import requests
from ops.model import Container

logger = logging.getLogger(__name__)


class OpenFGA:
    """Helper object for managing openfga."""

    def __init__(self, openfga_http_url: str, container: Container) -> None:
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

        if not stderr:
            raise RuntimeError("Couldn't retrieve app version")

        # Output has the format:
        # {datetime} OpenFGA version `{version}` build from `{hash}` on `{timestamp}`
        out_re = r"OpenFGA version `(.+)` build from `(.+)` on `(.+)`"
        versions = re.findall(out_re, stderr)[0]
        return versions[0]

    def create_store(self, token: str, store_name: str) -> Dict:
        """Create a store."""
        headers = {"Authorization": "Bearer {}".format(token)}
        r = requests.post(
            "{}/stores".format(self.openfga_http_url),
            json={"name": store_name},
            headers=headers,
            verify=False,
        )
        r.raise_for_status()

        return r.json()

    def list_stores(self, token: str, continuation_token: Optional[str] = None) -> Dict:
        """Get a list of the stores."""
        headers = {"Authorization": "Bearer {}".format(token)}
        url = "{}/stores".format(self.openfga_http_url)
        if continuation_token:
            url = url + f"?continuation_token={continuation_token}"
        r = requests.get(
            url,
            headers=headers,
            verify=False,
        )
        r.raise_for_status()

        return r.json()

    def _run_cmd(
        self,
        cmd: List[str],
        timeout: float = 20,
        input_: Optional[str] = None,
        environment: Optional[Dict] = None,
    ) -> Tuple[str, Optional[str]]:
        logger.debug(f"Running cmd: {cmd}")
        process = self.container.exec(cmd, stdin=input_, environment=environment, timeout=timeout)
        output, stderr = process.wait_output()

        return (
            output.decode() if isinstance(output, bytes) else output,
            stderr.decode() if isinstance(stderr, bytes) else stderr,
        )
