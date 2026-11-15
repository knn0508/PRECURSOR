"""Refuse synthetic fixtures at the ingest choke points unless explicitly allowed (ALLOW_SYNTHETIC_INPUTS=true, tests only).

Production runs must process real files only. Synthetic generators write files carrying a tag; every reader that sees the tag calls
`refuse_if_synthetic`, so a tagged file placed in the data root is rejected instead of being processed and merely labelled.
"""
from app.core.config import get_settings


def refuse_if_synthetic(is_synthetic: bool, exc_type: type[Exception], what: str) -> None:
    if is_synthetic and not get_settings().allow_synthetic_inputs:
        raise exc_type(f"{what}: carries the synthetic-fixture tag and synthetic inputs are disabled (ALLOW_SYNTHETIC_INPUTS=false). Real data only.")
