from pathlib import Path
from typing import Any
from .atomic_io import write_json


def write_live_state(path: str | Path, payload: dict[str, Any]) -> None:
    """Publish a replaceable snapshot without forcing a disk sync per frame."""
    write_json(path, payload)
