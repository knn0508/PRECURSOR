"""Controlled execution of external scientific tools (SNAP gpt, ISCE, SNAPHU, ...). None is installed here.

Every run is availability-checked, version-logged, time-limited, output-validated, and never uses a shell.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.services.insar.types import BlockedMissingInput, ProcessingError

log = logging.getLogger(__name__)


@dataclass
class ExternalTool:
    name: str
    executables: tuple[str, ...]
    version_args: tuple[str, ...] = ("--version",)
    path: str | None = field(default=None, init=False)

    def locate(self) -> str | None:
        for exe in self.executables:
            found = shutil.which(exe)
            if found:
                self.path = found
                return found
        return None

    def available(self) -> bool:
        return self.locate() is not None

    def require(self) -> str:
        p = self.locate()
        if p is None:
            raise BlockedMissingInput(f"external tool '{self.name}' not found (looked for: {', '.join(self.executables)})")
        return p

    def version(self, timeout: int = 30) -> str | None:
        p = self.locate()
        if p is None:
            return None
        try:
            r = subprocess.run([p, *self.version_args], capture_output=True, text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None
        out = (r.stdout or r.stderr or "").strip().splitlines()
        return out[0][:200] if out else None

    def run(self, args: list[str], *, timeout: int, expected_outputs: list[Path] | None = None, cwd: Path | None = None) -> str:
        exe = self.require()
        log.info("running %s (timeout %ss)", self.name, timeout)
        try:
            r = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout, cwd=cwd, check=False)
        except subprocess.TimeoutExpired:
            raise ProcessingError(f"{self.name} timed out after {timeout}s") from None
        except OSError as exc:
            raise ProcessingError(f"{self.name} could not be executed: {exc}") from None
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or "").strip()[-500:]
            raise ProcessingError(f"{self.name} exited with code {r.returncode}: {tail}")
        for out in expected_outputs or []:
            if not out.exists() or out.stat().st_size == 0:
                raise ProcessingError(f"{self.name} finished but expected output is missing or empty: {out.name}")
        return r.stdout


SNAP_GPT = ExternalTool("ESA SNAP gpt", ("gpt", "gpt.exe"), ("-h",))
ISCE = ExternalTool("ISCE2 topsApp", ("topsApp.py",), ("--help",))
SNAPHU = ExternalTool("SNAPHU", ("snaphu",), ("-h",))
