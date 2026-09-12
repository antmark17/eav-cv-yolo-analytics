from pathlib import Path
import cv2
from .atomic_io import write_bytes


def write_live_jpeg(path: str | Path, frame, *, quality: int = 70) -> None:
    ok, encoded = cv2.imencode(
        ".jpg",
        frame,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)],
    )

    if not ok:
        return

    try:
        write_bytes(path, encoded.tobytes())
    except PermissionError:
        # Un frame perso nella preview non deve fermare
        # l'intera pipeline AI.
        return
