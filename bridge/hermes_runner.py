"""Hermes CLI subprocess runner."""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)


class HermesRunnerError(Exception):
    """Base runner error."""


class HermesTimeoutError(HermesRunnerError):
    """Hermes process timed out."""


class HermesExecutionError(HermesRunnerError):
    """Hermes process exited with non-zero."""


@dataclass(frozen=True)
class HermesResult:
    """Result of a Hermes CLI invocation."""

    stdout: str
    session_id: str | None
    usage: dict[str, Any]


class HermesRunner:
    """Executes the Hermes CLI without shell=True."""

    def __init__(
        self,
        hermes_bin: str = "hermes",
        profile: str = "default",
        provider: str | None = None,
        model: str | None = None,
        toolsets: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize runner."""
        self.hermes_bin = hermes_bin
        self.profile = profile
        self.provider = provider
        self.model = model
        self.toolsets = toolsets
        self.timeout = timeout

    def _build_args(
        self, prompt: str, usage_file: Path, resume_session_id: str | None = None
    ) -> list[str]:
        args = [
            self.hermes_bin,
            "-p",
            self.profile,
            "-z",
            prompt,
            "--usage-file",
            str(usage_file),
        ]
        if self.provider:
            args.extend(["--provider", self.provider])
        if self.model:
            args.extend(["-m", self.model])
        if self.toolsets:
            args.extend(["-t", self.toolsets])
        if resume_session_id:
            args.insert(1, "--resume")
            args.insert(2, resume_session_id)
        return args

    async def run(
        self, prompt: str, resume_session_id: str | None = None
    ) -> HermesResult:
        """Run Hermes CLI and parse usage output."""
        usage_file = Path(tempfile.gettempdir()) / f"hermes_usage_{uuid.uuid4().hex}.json"

        args = self._build_args(prompt, usage_file, resume_session_id)
        _LOGGER.debug("Running Hermes: %s", " ".join(args))

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError as err:
                proc.kill()
                await proc.wait()
                raise HermesTimeoutError(
                    f"Hermes process timed out after {self.timeout}s"
                ) from err
        except FileNotFoundError as err:
            raise HermesRunnerError(
                f"Hermes binary not found: {self.hermes_bin}"
            ) from err

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        usage: dict[str, Any] = {}
        if usage_file.exists():
            try:
                usage = json.loads(usage_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as err:
                _LOGGER.warning("Failed to parse usage file: %s", err)

        if proc.returncode != 0:
            _LOGGER.error(
                "Hermes exited %d\nstdout: %s\nstderr: %s",
                proc.returncode,
                stdout,
                stderr,
            )
            raise HermesExecutionError(
                f"Hermes exited with code {proc.returncode}: {stderr[:500]}"
            )

        session_id = usage.get("session_id")
        return HermesResult(stdout=stdout, session_id=session_id, usage=usage)
