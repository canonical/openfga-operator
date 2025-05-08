# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

import pytest
from ops.pebble import ExecError

from cli import CommandLine


class TestCommandLine:
    @pytest.fixture
    def command_line(self, mocked_container: MagicMock) -> CommandLine:
        return CommandLine(mocked_container)

    def test_get_openfga_service_version(self, command_line: CommandLine) -> None:
        expected = "v1.8.4"
        cmd_output = (
            "2025/05/05 20:30:38 OpenFGA version `v1.8.4` build from "
            "`dc1a4803b1ae2f539a67cfa78a929923642c631b` on2025-03-25T12:13:09Z`"
        )
        with patch.object(
            command_line,
            "_run_cmd",
            return_value=("", cmd_output),
        ) as run_cmd:
            actual = command_line.get_openfga_service_version()
            assert actual == expected
            run_cmd.assert_called_with(["openfga", "version"])

    def test_migrate(self, command_line: CommandLine) -> None:
        dsn = "postgres://user:password@localhost/db"
        with patch.object(command_line, "_run_cmd") as run_cmd:
            command_line.migrate(dsn)

        expected_cmd = [
            "openfga",
            "migrate",
            "--datastore-engine",
            "postgres",
            "--datastore-uri",
            dsn,
        ]
        run_cmd.assert_called_once_with(expected_cmd, timeout=60)

    def test_run_cmd(self, mocked_container: MagicMock, command_line: CommandLine) -> None:
        cmd, expected = ["cmd"], ("stdout", "")

        mocked_process = MagicMock(wait_output=MagicMock(return_value=expected))
        mocked_container.exec.return_value = mocked_process

        actual = command_line._run_cmd(cmd)

        assert actual == expected
        mocked_container.exec.assert_called_once_with(cmd, timeout=20, environment=None)

    def test_run_cmd_failed(self, mocked_container: MagicMock, command_line: CommandLine) -> None:
        cmd = ["cmd"]

        mocked_process = MagicMock(wait_output=MagicMock(side_effect=ExecError(cmd, 1, "", "")))
        mocked_container.exec.return_value = mocked_process

        with pytest.raises(ExecError):
            command_line._run_cmd(cmd)
