from __future__ import annotations

from dataclasses import dataclass
import math
import time
import uuid

import numpy as np

from .analytics import AnalyticsEvent
from .config import HealthConfig


@dataclass(slots=True)
class _ConditionState:
    since: float | None = None
    active: bool = False
    last_alert_at: float = -math.inf


class FrameHealthMonitor:
    """Detect common camera/pipeline failures without a second ML model."""

    def __init__(self, config: HealthConfig) -> None:
        self.config = config
        self._conditions = {
            name: _ConditionState()
            for name in ("offline", "black_frame", "frozen_frame", "blurred_frame", "low_fps")
        }
        self._previous_sample: np.ndarray | None = None
        self._last_frame_at: float | None = None

    def reset(self) -> None:
        self._previous_sample = None
        self._last_frame_at = None
        for state in self._conditions.values():
            state.since = None
            state.active = False

    @staticmethod
    def _event(timestamp: float, kind: str, details: dict[str, float | str]) -> AnalyticsEvent:
        return AnalyticsEvent(
            event_id=str(uuid.uuid4()),
            event_type="malfunction",
            timestamp=timestamp,
            severity="critical",
            details={"kind": kind, **details},
        )

    def _evaluate(
        self,
        *,
        kind: str,
        condition: bool,
        hold_s: float,
        timestamp: float,
        monotonic_now: float,
        details: dict[str, float | str],
    ) -> AnalyticsEvent | None:
        state = self._conditions[kind]
        if not condition:
            state.since = None
            state.active = False
            return None
        if state.since is None:
            state.since = monotonic_now
        if (
            monotonic_now - state.since >= hold_s
            and not state.active
            and monotonic_now - state.last_alert_at >= self.config.cooldown_s
        ):
            state.active = True
            state.last_alert_at = monotonic_now
            return self._event(timestamp, kind, details)
        return None

    @staticmethod
    def _luma(frame: np.ndarray) -> np.ndarray:
        if frame.ndim == 2:
            return frame.astype(np.float32)
        # OpenCV frames use BGR. Exact colorimetry is unnecessary for health.
        return (
            0.114 * frame[..., 0]
            + 0.587 * frame[..., 1]
            + 0.299 * frame[..., 2]
        ).astype(np.float32)

    @staticmethod
    def _focus_variance(gray: np.ndarray) -> float:
        if min(gray.shape[:2]) < 3:
            return 0.0
        horizontal = np.diff(gray, axis=1)
        vertical = np.diff(gray, axis=0)
        return float((np.var(horizontal) + np.var(vertical)) / 2.0)

    def observe(
        self,
        frame: np.ndarray,
        *,
        timestamp: float | None = None,
        monotonic_timestamp: float | None = None,
        processed_fps: float = 0.0,
    ) -> tuple[AnalyticsEvent, ...]:
        if not self.config.enabled:
            return ()
        now = time.time() if timestamp is None else float(timestamp)
        monotonic_now = (
            time.monotonic()
            if monotonic_timestamp is None
            else float(monotonic_timestamp)
        )
        self._last_frame_at = monotonic_now
        self._evaluate(
            kind="offline",
            condition=False,
            hold_s=self.config.offline_after_s,
            timestamp=now,
            monotonic_now=monotonic_now,
            details={},
        )

        gray = self._luma(frame)
        mean_luma = float(np.mean(gray))
        focus_variance = self._focus_variance(gray)
        sample = gray[:: max(1, gray.shape[0] // 32), :: max(1, gray.shape[1] // 32)]
        frozen_delta = math.inf
        if self._previous_sample is not None and self._previous_sample.shape == sample.shape:
            frozen_delta = float(np.mean(np.abs(sample - self._previous_sample)))
        self._previous_sample = sample.copy()

        checks = (
            (
                "black_frame",
                mean_luma <= self.config.black_luma_threshold,
                self.config.black_after_s,
                {"mean_luma": round(mean_luma, 3)},
            ),
            (
                "frozen_frame",
                frozen_delta <= self.config.frozen_mean_delta,
                self.config.frozen_after_s,
                {"mean_delta": round(frozen_delta, 5)},
            ),
            (
                "blurred_frame",
                focus_variance <= self.config.blur_variance_threshold,
                self.config.blur_after_s,
                {"focus_variance": round(focus_variance, 3)},
            ),
            (
                "low_fps",
                processed_fps > 0
                and processed_fps < self.config.low_fps_threshold,
                self.config.low_fps_after_s,
                {"processed_fps": round(processed_fps, 3)},
            ),
        )
        events: list[AnalyticsEvent] = []
        for kind, condition, hold_s, details in checks:
            event = self._evaluate(
                kind=kind,
                condition=condition,
                hold_s=hold_s,
                timestamp=now,
                monotonic_now=monotonic_now,
                details=details,
            )
            if event is not None:
                events.append(event)
        return tuple(events)

    def poll_offline(
        self,
        *,
        timestamp: float | None = None,
        monotonic_timestamp: float | None = None,
    ) -> tuple[AnalyticsEvent, ...]:
        if not self.config.enabled:
            return ()
        now = time.time() if timestamp is None else float(timestamp)
        monotonic_now = (
            time.monotonic()
            if monotonic_timestamp is None
            else float(monotonic_timestamp)
        )
        offline = (
            self._last_frame_at is not None
            and monotonic_now - self._last_frame_at >= self.config.offline_after_s
        )
        event = self._evaluate(
            kind="offline",
            condition=offline,
            hold_s=0.0,
            timestamp=now,
            monotonic_now=monotonic_now,
            details={
                "seconds_without_frame": round(
                    0.0
                    if self._last_frame_at is None
                    else monotonic_now - self._last_frame_at,
                    3,
                )
            },
        )
        return () if event is None else (event,)

    def model_failure(self, message: str, *, timestamp: float | None = None) -> AnalyticsEvent:
        return self._event(
            time.time() if timestamp is None else float(timestamp),
            "model_failure",
            {"message": message[:240]},
        )
