"""Processed-output layout for Phase 4 and safe path handling. Source files (data/raw, data/external) are only READ.

data/processed/environmental/<area_id>/{dem,rainfall,soil,land_cover,historical_landslides,seismic,insar,aligned,
                                          features,reports,intermediate}/
data/external/<provider>/       files the user placed or downloaded AFTER approving them (soilgrids, land_cover, ...)
"""
from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

SUBDIRS = ("dem", "rainfall", "soil", "land_cover", "historical_landslides", "seismic", "insar", "aligned",
           "features", "reports", "intermediate")
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def env_root(data_root: Path) -> Path:
    return data_root / "processed" / "environmental"


def area_dir(data_root: Path, area_id: uuid.UUID, sub: str | None = None) -> Path:
    if sub is not None and sub not in SUBDIRS:
        raise ValueError(f"unknown environmental subdirectory {sub!r}")
    d = env_root(data_root) / str(area_id) / (sub or "")
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_layout(data_root: Path) -> None:
    env_root(data_root).mkdir(parents=True, exist_ok=True)
    (data_root / "external").mkdir(parents=True, exist_ok=True)


def external_dir(data_root: Path, provider: str) -> Path:
    if not _SAFE.match(provider):
        raise ValueError("invalid provider directory name")
    return data_root / "external" / provider


def to_relative(data_root: Path, p: Path) -> str:
    return p.resolve().relative_to(data_root.resolve()).as_posix()


def resolve_output(data_root: Path, rel: str) -> Path:
    """A registered output path -> absolute; refused unless it stays inside data/processed/environmental."""
    p = (data_root / rel).resolve()
    if not p.is_relative_to(env_root(data_root).resolve()):
        raise ValueError("registered output path escapes processed/environmental")
    return p


def resolve_input_under(data_root: Path, rel_or_abs: str, *roots: str) -> Path:
    """An input file path (as stored by Phase 2 or the user) -> absolute, refused unless under one of `roots`
    (names relative to data_root, e.g. "raw", "external")."""
    p = Path(rel_or_abs)
    p = (p if p.is_absolute() else data_root / p).resolve()
    if not any(p.is_relative_to((data_root / r).resolve()) for r in roots):
        raise ValueError("input file is outside the allowed source directories")
    if not p.exists():
        raise FileNotFoundError(p.name)
    return p


def check_disk(path: Path, needed_bytes: int, min_free_bytes: int) -> None:
    free = shutil.disk_usage(path).free
    if free - needed_bytes < min_free_bytes:
        raise OSError(f"insufficient disk space: need ~{needed_bytes} B plus {min_free_bytes} B reserve, {free} B free")
