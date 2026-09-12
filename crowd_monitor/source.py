from __future__ import annotations

from dataclasses import dataclass
import os
import threading
import time
from typing import Any, Callable

import cv2
import numpy as np
import requests


class SourceUnavailable(RuntimeError):
    """Raised when no decodable frame can be received from the source."""


@dataclass(frozen=True, slots=True)
class FramePacket:
    frame: np.ndarray
    sequence: int
    captured_at: float
    observed_at: float
    source_generation: int
    source_latency_ms: float | None = None


def _is_network_source(uri: str | int) -> bool:
    return isinstance(uri, int) or str(uri).lower().startswith(
        ("http://", "https://", "rtsp://", "rtmp://")
    )


def _open_capture(
    uri: str | int,
    open_timeout_ms: int,
    read_timeout_ms: int,
) -> cv2.VideoCapture:
    if isinstance(uri, str) and uri.lower().startswith("rtsp://"):
        os.environ.setdefault(
            "OPENCV_FFMPEG_CAPTURE_OPTIONS",
            "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay",
        )

    params: list[int] = []
    if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
        params += [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(open_timeout_ms)]
    if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
        params += [cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(read_timeout_ms)]

    try:
        if params:
            cap = cv2.VideoCapture(uri, cv2.CAP_FFMPEG, params)
        else:
            cap = cv2.VideoCapture(uri)
    except (TypeError, cv2.error):
        cap = cv2.VideoCapture(uri)

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


class LatestFrameSource:
    """Background reader retaining only the newest frame."""

    def __init__(
        self,
        uri: str | int,
        reconnect_delay_s: float = 3.0,
        open_timeout_ms: int = 8_000,
        read_timeout_ms: int = 8_000,
        loop_file: bool = False,
    ) -> None:
        self.uri = uri
        self.reconnect_delay_s = reconnect_delay_s
        self.open_timeout_ms = open_timeout_ms
        self.read_timeout_ms = read_timeout_ms
        self.loop_file = loop_file

        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest: FramePacket | None = None
        self._sequence = 0
        self._generation = 0
        self._last_error: str | None = None
        self._connected = False

    @property
    def last_error(self) -> str | None:
        with self._condition:
            return self._last_error

    @property
    def connected(self) -> bool:
        with self._condition:
            return self._connected

    def start(self) -> "LatestFrameSource":
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._reader_loop,
            name="latest-frame-source",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(2.0, self.reconnect_delay_s + 1.0))

    def read(
        self,
        after_sequence: int | None = None,
        timeout_s: float = 2.0,
    ) -> FramePacket | None:
        deadline = time.monotonic() + timeout_s
        with self._condition:
            while not self._stop.is_set():
                packet = self._latest
                if packet is not None and (
                    after_sequence is None or packet.sequence > after_sequence
                ):
                    return FramePacket(
                        frame=packet.frame.copy(),
                        sequence=packet.sequence,
                        captured_at=packet.captured_at,
                        observed_at=packet.observed_at,
                        source_generation=packet.source_generation,
                        source_latency_ms=packet.source_latency_ms,
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(timeout=remaining)
        return None

    def wait_for_first_frame(self, timeout_s: float) -> FramePacket:
        packet = self.read(timeout_s=timeout_s)
        if packet is None:
            detail = self.last_error or "no decodable frames received"
            raise SourceUnavailable(
                f"Unable to receive a frame from {self.uri!r}: {detail}. "
                "Use the direct JPEG/MJPEG/HLS/RTSP endpoint rather than a "
                "camera web interface."
            )
        return packet

    def _resolve_uri(self) -> str | int:
        """Resolve the current capture URI before every open/reconnect."""

        return self.uri

    def _reader_loop(self) -> None:
        is_network = _is_network_source(self.uri)
        while not self._stop.is_set():
            try:
                resolved_uri = self._resolve_uri()
                cap = _open_capture(
                    resolved_uri,
                    self.open_timeout_ms,
                    self.read_timeout_ms,
                )
            except Exception as exc:
                with self._condition:
                    self._connected = False
                    self._last_error = f"source resolution failed: {exc}"
                    self._condition.notify_all()
                self._stop.wait(self.reconnect_delay_s)
                continue
            if not cap.isOpened():
                with self._condition:
                    self._connected = False
                    self._last_error = "OpenCV could not open the source"
                    self._condition.notify_all()
                cap.release()
                if not is_network and not self.loop_file:
                    return
                self._stop.wait(self.reconnect_delay_s)
                continue

            with self._condition:
                self._generation += 1
                generation = self._generation
                self._connected = True
                self._last_error = None
                self._condition.notify_all()

            received_any = False
            while not self._stop.is_set():
                read_started = time.monotonic()
                ok, frame = cap.read()
                read_elapsed_ms = (time.monotonic() - read_started) * 1000.0
                if not ok or frame is None or frame.size == 0:
                    with self._condition:
                        self._connected = False
                        self._last_error = "stream read failed or reached end of file"
                        self._condition.notify_all()
                    break

                received_any = True
                with self._condition:
                    self._sequence += 1
                    self._latest = FramePacket(
                        frame=frame,
                        sequence=self._sequence,
                        captured_at=time.monotonic(),
                        observed_at=time.time(),
                        source_generation=generation,
                        source_latency_ms=read_elapsed_ms,
                    )
                    self._condition.notify_all()

            cap.release()
            if self._stop.is_set():
                return
            if not is_network and not self.loop_file:
                return
            if not received_any:
                self._stop.wait(self.reconnect_delay_s)

    def __enter__(self) -> "LatestFrameSource":
        return self.start()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop()


class HttpSnapshotSource(LatestFrameSource):
    """Acquire repeated JPEG snapshots over HTTP."""

    def __init__(
        self,
        uri: str,
        target_fps: float = 3.0,
        snapshot_timeout_s: float = 5.0,
        reconnect_delay_s: float = 1.0,
    ) -> None:
        super().__init__(
            uri=uri,
            reconnect_delay_s=reconnect_delay_s,
            open_timeout_ms=0,
            read_timeout_ms=0,
            loop_file=False,
        )
        self.target_fps = max(0.1, target_fps)
        self.snapshot_timeout_s = snapshot_timeout_s

    def _reader_loop(self) -> None:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0",
                "Accept": "image/jpeg,*/*",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Connection": "keep-alive",
            }
        )
        interval = 1.0 / self.target_fps

        try:
            while not self._stop.is_set():
                cycle_started = time.monotonic()
                try:
                    response = session.get(
                        str(self.uri),
                        params={"_": time.time_ns()},
                        timeout=(3.0, self.snapshot_timeout_s),
                    )
                    response.raise_for_status()
                    image_buffer = np.frombuffer(response.content, dtype=np.uint8)
                    frame = cv2.imdecode(image_buffer, cv2.IMREAD_COLOR)
                    if frame is None or frame.size == 0:
                        raise ValueError("The response does not contain a valid JPEG")

                    received_at = time.monotonic()
                    with self._condition:
                        if not self._connected:
                            self._generation += 1
                        self._connected = True
                        self._last_error = None
                        self._sequence += 1
                        self._latest = FramePacket(
                            frame=frame,
                            sequence=self._sequence,
                            captured_at=cycle_started,
                            observed_at=time.time(),
                            source_generation=self._generation,
                            source_latency_ms=(received_at - cycle_started) * 1000.0,
                        )
                        self._condition.notify_all()

                except (requests.RequestException, ValueError) as exc:
                    with self._condition:
                        self._connected = False
                        self._last_error = str(exc)
                        self._condition.notify_all()
                    self._stop.wait(self.reconnect_delay_s)
                    continue

                remaining = interval - (time.monotonic() - cycle_started)
                if remaining > 0:
                    self._stop.wait(remaining)
        finally:
            session.close()


def resolve_youtube_stream_url(
    page_url: str,
    *,
    max_height: int = 720,
    cookies_from_browser: str | None = None,
    extractor: Callable[[str, dict[str, Any]], str] | None = None,
) -> str:
    """Resolve a YouTube page to a temporary live media URL.

    The returned URL is deliberately not cached across reconnects. YouTube
    media URLs expire, so ``YoutubeLiveSource`` invokes this function before
    every attempt to reopen the capture.
    """

    if not isinstance(page_url, str) or not any(
        marker in page_url.lower() for marker in ("youtube.com/", "youtu.be/")
    ):
        raise ValueError("Expected a youtube.com video URL")
    if max_height <= 0:
        raise ValueError("max_height must be greater than zero")

    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": f"best[height<={max_height}]/best",
    }
    if cookies_from_browser:
        options["cookiesfrombrowser"] = (cookies_from_browser,)
    if extractor is not None:
        resolved = extractor(page_url, options)
    else:
        try:
            from yt_dlp import YoutubeDL
        except ImportError as exc:
            raise RuntimeError(
                "YouTube mode requires yt-dlp. Install the project dependencies."
            ) from exc
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(page_url, download=False)
        if not isinstance(info, dict):
            raise RuntimeError("yt-dlp returned no video information")
        resolved = info.get("url")
        if not resolved:
            requested = info.get("requested_downloads") or info.get(
                "requested_formats"
            )
            if isinstance(requested, list):
                video = next(
                    (
                        item.get("url")
                        for item in requested
                        if isinstance(item, dict)
                        and item.get("url")
                        and item.get("vcodec") != "none"
                    ),
                    None,
                )
                resolved = video
    if not isinstance(resolved, str) or not resolved.startswith(
        ("http://", "https://")
    ):
        raise RuntimeError("yt-dlp did not return a usable HTTP media URL")
    return resolved


class YoutubeLiveSource(LatestFrameSource):
    """Resolve and read the current point of a YouTube live stream."""

    def __init__(
        self,
        uri: str,
        *,
        max_height: int = 720,
        cookies_from_browser: str | None = None,
        reconnect_delay_s: float = 5.0,
        open_timeout_ms: int = 12_000,
        read_timeout_ms: int = 12_000,
        resolver: Callable[..., str] = resolve_youtube_stream_url,
    ) -> None:
        super().__init__(
            uri=uri,
            reconnect_delay_s=reconnect_delay_s,
            open_timeout_ms=open_timeout_ms,
            read_timeout_ms=read_timeout_ms,
            loop_file=False,
        )
        self.max_height = max_height
        self.cookies_from_browser = cookies_from_browser
        self._resolver = resolver

    def _resolve_uri(self) -> str:
        return self._resolver(
            str(self.uri),
            max_height=self.max_height,
            cookies_from_browser=self.cookies_from_browser,
        )


def probe_snapshot_source(
    uri: str,
    timeout_s: float = 8.0,
) -> dict[str, Any]:
    """Fetch and decode one JPEG snapshot."""
    started = time.monotonic()
    try:
        response = requests.get(
            uri,
            params={"_": time.time_ns()},
            timeout=(3.0, timeout_s),
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "image/jpeg,*/*",
                "Cache-Control": "no-cache",
            },
        )
        response.raise_for_status()
        frame = cv2.imdecode(
            np.frombuffer(response.content, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        if frame is None or frame.size == 0:
            raise ValueError("The response does not contain a valid JPEG")
    except (requests.RequestException, ValueError) as exc:
        return {
            "ok": False,
            "mode": "snapshot",
            "source": uri,
            "error": str(exc),
            "elapsed_s": round(time.monotonic() - started, 3),
        }

    height, width = frame.shape[:2]
    return {
        "ok": True,
        "mode": "snapshot",
        "source": uri,
        "width": int(width),
        "height": int(height),
        "elapsed_s": round(time.monotonic() - started, 3),
        "frame": frame,
    }


def probe_source(
    uri: str | int,
    timeout_s: float = 8.0,
    open_timeout_ms: int = 5_000,
    read_timeout_ms: int = 5_000,
) -> dict[str, Any]:
    """Try to open a stream source and decode one frame."""
    started = time.monotonic()
    cap = _open_capture(uri, open_timeout_ms, read_timeout_ms)
    if not cap.isOpened():
        cap.release()
        return {
            "ok": False,
            "source": str(uri),
            "error": "OpenCV could not open the source",
            "elapsed_s": round(time.monotonic() - started, 3),
        }

    ok = False
    frame = None
    while time.monotonic() - started < timeout_s:
        ok, frame = cap.read()
        if ok and frame is not None and frame.size:
            break
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    cap.release()

    if not ok or frame is None or not frame.size:
        return {
            "ok": False,
            "source": str(uri),
            "error": "source opened, but no frame could be decoded",
            "elapsed_s": round(time.monotonic() - started, 3),
        }

    height, width = frame.shape[:2]
    return {
        "ok": True,
        "source": str(uri),
        "width": int(width),
        "height": int(height),
        "reported_fps": fps,
        "elapsed_s": round(time.monotonic() - started, 3),
        "frame": frame,
    }
