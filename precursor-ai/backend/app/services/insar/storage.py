"""Processed-output layout and safe path handling. Raw inputs are only ever READ.

data/processed/insar/{inspections,coherence,displacement,velocity,quality_reports,metadata,intermediate}/<run_id>/
data/samples/insar/            labelled synthetic fixtures / explicitly placed local inputs
"""
from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from app.services.insar.types import ProcessingError, ProductType

SUBDIRS = ("inspections", "coherence", "displacement", "velocity", "quality_reports", "metadata", "intermediate")
KIND_DIR = {
    ProductType.LOS_DISPLACEMENT: "displacement",
    ProductType.COHERENCE: "coherence",
    ProductType.LOS_VELOCITY: "velocity",
}
_SAFE_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def insar_root(data_root: Path) -> Path:
    return data_root / "processed" / "insar"


def samples_dir(data_root: Path) -> Path:
    return data_root / "samples" / "insar"


def ensure_layout(data_root: Path) -> None:
    for s in SUBDIRS:
        (insar_root(data_root) / s).mkdir(parents=True, exist_ok=True)
    samples_dir(data_root).mkdir(parents=True, exist_ok=True)


def run_dir(data_root: Path, sub: str, run_id: uuid.UUID) -> Path:
    d = insar_root(data_root) / sub / str(run_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def to_relative(data_root: Path, p: Path) -> str:
    return p.resolve().relative_to(data_root.resolve()).as_posix()


def resolve_output(data_root: Path, rel: str) -> Path:
    """A registered output path -> absolute, refused unless it stays inside data/processed/insar."""
    p = (data_root / rel).resolve()
    if not p.is_relative_to(insar_root(data_root).resolve()):
        raise ProcessingError("registered output path escapes the processed/insar directory")
    return p


def resolve_sample(data_root: Path, name: str) -> Path:
    """A bare file name inside data/samples/insar. No separators, no traversal."""
    if not _SAFE_FILE.match(name) or name.startswith(".."):
        raise ValueError("invalid sample file name")
    p = samples_dir(data_root) / name
    if not p.is_file():
        raise FileNotFoundError(name)
    return p


def resolve_acquisition_file(data_root: Path, local_file_path: str) -> Path:
    """Phase 2 stores raw files under data/raw; only those may be used as acquisition inputs."""
    raw = (data_root / "raw").resolve()
    p = Path(local_file_path)
    p = (p if p.is_absolute() else data_root / p).resolve()
    if not p.is_relative_to(raw):
        raise ProcessingError("acquisition file is outside data/raw")
    if not p.exists():
        raise FileNotFoundError(p.name)
    return p


def check_disk(path: Path, needed_bytes: int, min_free_bytes: int) -> None:
    free = shutil.disk_usage(path).free
    if free - needed_bytes < min_free_bytes:
        raise ProcessingError(
            f"insufficient disk space: need ~{needed_bytes} B plus {min_free_bytes} B reserve, {free} B free"
        )
