""".. include:: ../../README.md"""  # noqa: D415

import logging
import os
import pathlib as pl
import shlex
import typing
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from subprocess import PIPE, Popen

from styxdefs import (
    Execution,
    InputPathType,
    Metadata,
    OutputPathType,
    Runner,
    StyxRuntimeError,
)

if os.name == "posix":
    _HOST_UID: int | None = os.getuid()  # type: ignore
else:
    _HOST_UID = None


def _podman_mount(host_path: str, container_path: str, readonly: bool) -> str:
    """Construct Podman mount argument."""
    host_path = host_path.replace('"', r"\"")
    container_path = container_path.replace('"', r"\"")
    host_path = host_path.replace("\\", "\\\\")
    container_path = container_path.replace("\\", "\\\\")
    readonly_str = ",readonly" if readonly else ""
    return f"type=bind,source={host_path},target={container_path}{readonly_str}"


class StyxPodmanError(StyxRuntimeError):
    """Styx Podman runtime error."""

    def __init__(
        self,
        return_code: int | None = None,
        command_args: list[str] | None = None,
        podman_args: list[str] | None = None,
    ) -> None:
        """Create StyxPodmanError."""
        super().__init__(
            return_code=return_code,
            command_args=command_args,
            message_extra=f"- Podman args: {shlex.join(podman_args)}"
            if podman_args
            else None,
        )


class _PodmanExecution(Execution):
    """Podman execution."""

    def __init__(
        self,
        logger: logging.Logger,
        output_dir: pl.Path,
        metadata: Metadata,
        container_tag: str,
        podman_executable: str,
        podman_extra_args: list[str],
        podman_user_id: int | None,
        environ: dict[str, str],
    ) -> None:
        """Create PodmanExecution."""
        self.logger: logging.Logger = logger
        self.input_mounts: list[tuple[pl.Path, str, bool]] = []
        self.input_file_next_id = 0
        self.output_dir = output_dir
        self.metadata = metadata
        self.container_tag = container_tag
        self.podman_executable = podman_executable
        self.podman_extra_args = podman_extra_args
        self.podman_user_id = podman_user_id
        self.environ = environ

    def input_file(
        self,
        host_file: InputPathType,
        resolve_parent: bool = False,
        mutable: bool = False,
    ) -> str:
        """Resolve input file."""
        _host_file = pl.Path(host_file)

        if resolve_parent:
            _host_file_parent = _host_file.parent
            if not _host_file_parent.is_dir():
                # If Podman gets passed a file to mount which does not exist it will
                # create a directory at this location.
                # This odd behaviour can lead to cryptic error messages downstream so we
                # make sure to catch this early.
                raise FileNotFoundError(
                    f'Input folder not found: "{_host_file_parent}"'
                )

            local_file = (
                f"/styx_input/{self.input_file_next_id}/{_host_file_parent.name}"
            )
            resolved_file = f"{local_file}/{_host_file.name}"
            self.input_mounts.append((_host_file_parent, local_file, mutable))
        else:
            if not _host_file.exists():
                # See note above.
                # We don't know if the 'file' here is a directory or file
                # so we can't additionally assert that it is.
                raise FileNotFoundError(f'Input file not found: "{_host_file}"')

            resolved_file = local_file = (
                f"/styx_input/{self.input_file_next_id}/{_host_file.name}"
            )
            self.input_mounts.append((_host_file, local_file, mutable))

        self.input_file_next_id += 1
        return resolved_file

    def output_file(self, local_file: str, optional: bool = False) -> OutputPathType:
        """Resolve output file."""
        return self.output_dir / local_file

    def params(self, params: dict) -> dict:
        """No changes to params."""
        return params

    def run(
        self,
        cargs: list[str],
        handle_stdout: typing.Callable[[str], None] | None = None,
        handle_stderr: typing.Callable[[str], None] | None = None,
    ) -> None:
        """Execute."""
        mounts: list[str] = []

        for host_file, local_file, mutable in self.input_mounts:
            mounts.append("--mount")
            mounts.append(
                _podman_mount(
                    host_file.absolute().as_posix(), local_file, readonly=not mutable
                )
            )

        # Output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Create run script
        run_script = self.output_dir / "run.sh"
        # Ensure utf-8 encoding and unix newlines
        run_script.write_text(
            f"#!/bin/bash\n{shlex.join(cargs)}\n", encoding="utf-8", newline="\n"
        )

        mounts.append("--mount")
        mounts.append(
            _podman_mount(
                self.output_dir.absolute().as_posix(), "/styx_output", readonly=False
            )
        )

        environ_arg_args: list[str] = []
        for key, value in self.environ.items():
            environ_arg_args.extend(["--env", f"{key}={value}"])

        podman_command: list[str] = [
            self.podman_executable,
            "run",
            *self.podman_extra_args,
            "--rm",
            "--name",
            f"styx_{self.output_dir.name}",
            *(
                ["-u", str(self.podman_user_id)]
                if self.podman_user_id is not None
                else []
            ),
            "-w",
            "/styx_output",
            *mounts,
            "--entrypoint",
            "/bin/bash",
            *environ_arg_args,
            self.container_tag,
            "./run.sh",
        ]

        self.logger.debug(f"Running podman: {shlex.join(podman_command)}")
        self.logger.debug(f"Running command: {shlex.join(cargs)}")

        _stdout_handler = (
            handle_stdout if handle_stdout else lambda line: self.logger.info(line)
        )
        _stderr_handler = (
            handle_stderr if handle_stderr else lambda line: self.logger.error(line)
        )

        time_start = datetime.now()
        with Popen(podman_command, text=True, stdout=PIPE, stderr=PIPE) as process:
            with ThreadPoolExecutor(2) as pool:  # two threads to handle the streams
                exhaust = partial(pool.submit, partial(deque, maxlen=0))
                exhaust(_stdout_handler(line[:-1]) for line in process.stdout)  # type: ignore
                exhaust(_stderr_handler(line[:-1]) for line in process.stderr)  # type: ignore
        return_code = process.poll()
        time_end = datetime.now()
        self.logger.info(
            f"Executed {self.metadata.package} {self.metadata.name} "
            f"in {time_end - time_start}"
        )
        if return_code:
            raise StyxPodmanError(return_code, cargs, podman_command)


class PodmanRunner(Runner):
    """Podman runner."""

    logger_name = "styx_podman_runner"

    def __init__(
        self,
        image_overrides: dict[str, str] | None = None,
        podman_executable: str = "podman",
        podman_extra_args: list[str] | None = None,
        podman_user_id: int | None = None,
        data_dir: InputPathType | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        """Create a new PodmanRunner."""
        self.data_dir = pl.Path(data_dir or "styx_tmp")
        self.uid = os.urandom(8).hex()
        self.execution_counter = 0
        self.podman_executable = podman_executable
        self.podman_extra_args = podman_extra_args or []
        self.podman_user_id = (
            podman_user_id if podman_user_id is not None else _HOST_UID
        )
        self.image_overrides = image_overrides or {}
        self.environ = environ or {}

        # Configure logger
        self.logger = logging.getLogger(self.logger_name)
        if not self.logger.hasHandlers():
            self.logger.setLevel(logging.DEBUG)
            ch = logging.StreamHandler()
            ch.setLevel(logging.DEBUG)
            formatter = logging.Formatter("[%(levelname).1s] %(message)s")
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)

    def start_execution(self, metadata: Metadata) -> Execution:
        """Start execution."""
        if metadata.container_image_tag is None:
            raise ValueError("No container image tag specified in metadata")
        container_tag = self.image_overrides.get(
            metadata.container_image_tag, metadata.container_image_tag
        )
        if container_tag.startswith("docker://"):
            container_tag = container_tag.replace("docker://", "docker.io/", 1)
        elif not container_tag.startswith("docker.io/"):
            container_tag = f"docker.io/{container_tag}"

        self.execution_counter += 1
        return _PodmanExecution(
            logger=self.logger,
            output_dir=self.data_dir
            / f"{self.uid}_{self.execution_counter - 1}_{metadata.name}",
            metadata=metadata,
            container_tag=container_tag,
            podman_user_id=self.podman_user_id,
            podman_executable=self.podman_executable,
            podman_extra_args=self.podman_extra_args,
            environ=self.environ,
        )
