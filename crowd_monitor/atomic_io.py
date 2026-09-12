"""Atomic publication shared by snapshots and persistent operator state."""

from pathlib import Path
import json
import os
import tempfile
import time


def write_bytes(
    path: str | Path,
    data: bytes,
    *,
    durable: bool = False,
) -> None:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, temporary = tempfile.mkstemp(
        prefix=target.name + ".",
        suffix=".tmp",
        dir=target.parent,
    )

    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)

            if durable:
                handle.flush()
                os.fsync(handle.fileno())

        # Su Windows/OneDrive il file può essere temporaneamente bloccato.
        # Ritentiamo invece di terminare immediatamente la pipeline.
        for attempt in range(6):
            try:
                os.replace(temporary, target)
                return

            except PermissionError:
                if attempt == 5:
                    raise

                time.sleep(0.02 * (attempt + 1))

    finally:
        Path(temporary).unlink(missing_ok=True)


def write_json(
    path: str | Path,
    payload: object,
    *,
    durable: bool = False,
) -> None:
    data = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    write_bytes(
        path,
        data,
        durable=durable,
    )