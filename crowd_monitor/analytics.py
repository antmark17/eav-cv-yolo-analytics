from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any
import math
import time
import uuid

import numpy as np

from .config import AnalyticsConfig
from .detector import Detection
from .geometry import (
    euclidean_distance,
    normalized_line_to_pixels,
    normalized_to_pixels,
    point_in_polygon,
    segments_intersect,
    signed_distance_to_line,
)

PointPx = tuple[int, int]
TimedPoint = tuple[float, PointPx]


@dataclass(slots=True)
class TrackState:
    history: deque[TimedPoint]
    last_seen: float
    bbox: tuple[int, int, int, int]
    confidence: float
    class_id: int
    class_name: str


@dataclass(slots=True)
class ZoneTrackState:
    seen_inside: bool = False
    counted: bool = False
    last_seen: float = 0.0


@dataclass(slots=True)
class LineTrackState:
    last_side: int = 0
    last_side_point: PointPx | None = None
    last_crossing_at: float = -math.inf
    last_seen: float = 0.0


@dataclass(slots=True)
class RestrictedTrackState:
    inside: bool = False
    entered_at: float | None = None
    last_alert_at: float = -math.inf
    last_seen: float = 0.0


@dataclass(slots=True)
class CrowdAlertState:
    candidate_level: str = "normal"
    candidate_since: float = 0.0
    active_level: str = "normal"
    last_alert_at: float = -math.inf


@dataclass(slots=True)
class LuggageTrackState:
    candidate_track_id: int | None = None
    candidate_since: float | None = None
    owner_track_id: int | None = None
    owner_last_seen: float | None = None
    owner_last_position: PointPx | None = None
    reassociation_candidate_id: int | None = None
    reassociation_candidate_since: float | None = None
    owner_switches: int = 0
    unattended_since: float | None = None
    episode_id: str | None = None
    alerted: bool = False
    last_alert_at: float = -math.inf
    last_seen: float = 0.0


@dataclass(slots=True)
class AssociationTrackState:
    candidate_track_id: int | None = None
    candidate_since: float | None = None
    owner_track_id: int | None = None
    owner_last_seen: float | None = None
    owner_last_position: PointPx | None = None
    reassociation_candidate_id: int | None = None
    reassociation_candidate_since: float | None = None
    owner_switches: int = 0
    unsupervised_since: float | None = None
    episode_id: str | None = None
    alerted: bool = False
    last_alert_at: float = -math.inf
    last_seen: float = 0.0


@dataclass(slots=True)
class TimedAlertState:
    condition_since: float | None = None
    alerted: bool = False
    last_alert_at: float = -math.inf
    last_seen: float = 0.0


@dataclass(slots=True)
class TrainState:
    value: str = "UNKNOWN"
    candidate: str = "UNKNOWN"
    candidate_since: float = 0.0


@dataclass(frozen=True, slots=True)
class AnalyticsEvent:
    event_id: str
    event_type: str
    timestamp: float
    severity: str
    track_id: int | None = None
    zone: str | None = None
    direction: str | None = None
    object_class: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "severity": self.severity,
            "track_id": self.track_id,
            "zone": self.zone,
            "direction": self.direction,
            "object_class": self.object_class,
            "details": self.details,
        }


@dataclass(frozen=True, slots=True)
class ZoneSnapshot:
    name: str
    kind: str
    people: int
    density_people_m2: float | None
    level: str | None
    polygon_px: np.ndarray
    color: tuple[int, int, int]
    live_directions: dict[str, int] = field(default_factory=dict)
    cumulative_directions: dict[str, int] = field(default_factory=dict)
    stationary: int = 0


@dataclass(frozen=True, slots=True)
class LineSnapshot:
    name: str
    start: PointPx
    end: PointPx
    color: tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class TrackView:
    track_id: int
    class_id: int
    class_name: str
    bbox: tuple[int, int, int, int]
    confidence: float
    point: PointPx
    history: tuple[PointPx, ...]


@dataclass(frozen=True, slots=True)
class LuggageAssociationView:
    luggage_track_id: int
    owner_track_id: int | None
    candidate_track_id: int | None
    status: str
    case: str
    owner_distance_norm: float | None
    unattended_for_s: float


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    frame_index: int
    timestamp: float
    people: int
    objects: dict[str, int]
    train_state: str
    density_people_m2: float | None
    zones: tuple[ZoneSnapshot, ...]
    lines: tuple[LineSnapshot, ...]
    tracks: tuple[TrackView, ...]
    luggage_associations: tuple[LuggageAssociationView, ...]
    events: tuple[AnalyticsEvent, ...]
    roi_px: np.ndarray

    def to_dict(
        self,
        *,
        inference_fps: float | None = None,
        pipeline_latency_ms: float | None = None,
        performance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "frame_index": self.frame_index,
            "timestamp": self.timestamp,
            "people": self.people,
            "objects": dict(self.objects),
            "train_state": self.train_state,
            "density_people_m2": self.density_people_m2,
            "zones": [
                {
                    "name": zone.name,
                    "kind": zone.kind,
                    "people": zone.people,
                    "density_people_m2": zone.density_people_m2,
                    "level": zone.level,
                    "live_directions": zone.live_directions,
                    "cumulative_directions": zone.cumulative_directions,
                    "stationary": zone.stationary,
                }
                for zone in self.zones
            ],
            "luggage_associations": [
                {
                    "luggage_track_id": item.luggage_track_id,
                    "owner_track_id": item.owner_track_id,
                    "candidate_track_id": item.candidate_track_id,
                    "status": item.status,
                    "case": item.case,
                    "owner_distance_norm": item.owner_distance_norm,
                    "unattended_for_s": item.unattended_for_s,
                }
                for item in self.luggage_associations
            ],
            "events": [event.to_dict() for event in self.events],
        }
        perf = dict(performance or {})
        if inference_fps is not None:
            perf.setdefault("inference_fps", round(inference_fps, 3))
        if pipeline_latency_ms is not None:
            perf.setdefault("pipeline_latency_ms", round(pipeline_latency_ms, 2))
        if perf:
            payload["performance"] = perf
        return payload


class CrowdAnalyticsEngine:
    def __init__(self, config: AnalyticsConfig) -> None:
        self.config = config
        if config.reference_point not in {"center", "bottom_center"}:
            raise ValueError("reference_point must be 'center' or 'bottom_center'")

        self._tracks: dict[int, TrackState] = {}
        self._zone_states: dict[tuple[str, int], ZoneTrackState] = {}
        self._line_states: dict[tuple[str, int], LineTrackState] = {}
        self._restricted_states: dict[tuple[str, int], RestrictedTrackState] = {}
        self._crowd_states: dict[str, CrowdAlertState] = {}
        self._luggage_states: dict[int, LuggageTrackState] = {}
        self._animal_states: dict[int, AssociationTrackState] = {}
        self._litter_states: dict[int, TimedAlertState] = {}
        self._danger_states: dict[int, TimedAlertState] = {}
        self._vandalism_states: dict[int, TimedAlertState] = {}
        self._fall_states: dict[int, TimedAlertState] = {}
        self._train_state = TrainState()
        self._cumulative: dict[str, dict[str, int]] = {
            zone.name: {
                zone.direction_labels[0]: 0,
                zone.direction_labels[1]: 0,
            }
            for zone in config.zones
        }
        self._frame_index = 0
        # Analytics history is deliberately independent from the short visual
        # tail. A four-second stationarity rule must still work with a three-
        # point tail at high FPS.
        self._analytics_history_s = max(
            30.0,
            config.track_ttl_s + 2.0,
            config.luggage.stationary_s + 2.0,
            config.litter.stationary_s + 2.0,
        )

    def clear_transient_state(self) -> None:
        """Clear active state after a source reconnect or scene change."""
        self._tracks.clear()
        self._zone_states.clear()
        self._line_states.clear()
        self._restricted_states.clear()
        self._crowd_states.clear()
        self._luggage_states.clear()
        self._animal_states.clear()
        self._litter_states.clear()
        self._danger_states.clear()
        self._vandalism_states.clear()
        self._fall_states.clear()
        self._train_state = TrainState()

    def _reference_point(self, detection: Detection) -> PointPx:
        x1, y1, x2, y2 = detection.bbox
        x = (x1 + x2) // 2
        if (
            self.config.reference_point == "bottom_center"
            and detection.class_id in self.config.person_class_ids
        ):
            return (x, y2)
        return (x, (y1 + y2) // 2)

    @staticmethod
    def _bbox_center(bbox: tuple[int, int, int, int]) -> PointPx:
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    @staticmethod
    def _history_points(history: deque[TimedPoint]) -> list[PointPx]:
        return [point for _, point in history]

    @staticmethod
    def _axis_delta(
        history: deque[TimedPoint],
        axis: str,
        frame_width: int,
        frame_height: int,
        length: int,
    ) -> float:
        sample = list(history)[-length:]
        if len(sample) < 2:
            return 0.0
        axis_index = 0 if axis == "x" else 1
        scale = frame_width if axis == "x" else frame_height
        if scale <= 0:
            return 0.0
        return (
            sample[-1][1][axis_index] - sample[0][1][axis_index]
        ) / float(scale)

    @staticmethod
    def _event(
        *,
        event_type: str,
        timestamp: float,
        severity: str,
        track_id: int | None = None,
        zone: str | None = None,
        direction: str | None = None,
        object_class: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AnalyticsEvent:
        return AnalyticsEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=timestamp,
            severity=severity,
            track_id=track_id,
            zone=zone,
            direction=direction,
            object_class=object_class,
            details=details or {},
        )

    @staticmethod
    def _density_level(
        density: float | None,
        warning: float | None,
        critical: float | None,
    ) -> str | None:
        if density is None:
            return None
        if critical is not None and density >= critical:
            return "critical"
        if warning is not None and density >= warning:
            return "warning"
        return "normal"

    @staticmethod
    def _is_stationary(
        track: TrackState,
        monotonic_now: float,
        frame_diagonal: float,
        stationary_s: float,
        max_motion_norm: float,
    ) -> tuple[bool, float]:
        if stationary_s <= 0:
            return True, 0.0
        cutoff = monotonic_now - stationary_s
        anchor_index: int | None = None
        for index, (at, _) in enumerate(track.history):
            if at <= cutoff:
                anchor_index = index
            else:
                break
        if anchor_index is None:
            return False, 0.0
        window = list(track.history)[anchor_index:]
        anchor = window[0][1]
        max_motion = max(euclidean_distance(anchor, point) for _, point in window)
        motion_norm = max_motion / max(frame_diagonal, 1.0)
        return motion_norm <= max_motion_norm, motion_norm

    @staticmethod
    def _stable_candidate(
        state: LuggageTrackState,
        candidate_id: int | None,
        monotonic_now: float,
        confirm_s: float,
        *,
        reassociation: bool = False,
    ) -> bool:
        id_attr = (
            "reassociation_candidate_id" if reassociation else "candidate_track_id"
        )
        since_attr = (
            "reassociation_candidate_since" if reassociation else "candidate_since"
        )
        previous_id = getattr(state, id_attr)
        if candidate_id is None:
            setattr(state, id_attr, None)
            setattr(state, since_attr, None)
            return False
        if previous_id != candidate_id:
            setattr(state, id_attr, candidate_id)
            setattr(state, since_attr, monotonic_now)
        since = getattr(state, since_attr)
        return since is not None and monotonic_now - since >= confirm_s

    @staticmethod
    def _nearest_person_to_point(
        point: PointPx,
        persons: list[tuple[Detection, PointPx]],
        frame_diagonal: float,
    ) -> tuple[int | None, float | None]:
        if not persons:
            return None, None
        candidates = [
            (
                detection.track_id,
                euclidean_distance(
                    point, CrowdAnalyticsEngine._bbox_center(detection.bbox)
                )
                / max(frame_diagonal, 1.0),
            )
            for detection, _ in persons
        ]
        return min(candidates, key=lambda item: item[1])

    @staticmethod
    def _nearest_person(
        center: PointPx,
        persons: list[tuple[Detection, PointPx]],
        frame_diagonal: float,
    ) -> tuple[int | None, float | None]:
        if not persons:
            return None, None
        candidates = [
            (
                detection.track_id,
                euclidean_distance(
                    center,
                    CrowdAnalyticsEngine._bbox_center(detection.bbox),
                )
                / max(frame_diagonal, 1.0),
            )
            for detection, _ in persons
        ]
        return min(candidates, key=lambda item: item[1])

    @staticmethod
    def _inside_optional_polygon(point: PointPx, polygon: np.ndarray) -> bool:
        return not polygon.size or point_in_polygon(point, polygon)

    def process(
        self,
        detections: list[Detection],
        frame_shape: tuple[int, ...],
        timestamp: float | None = None,
        monotonic_timestamp: float | None = None,
    ) -> AnalysisResult:
        now = time.time() if timestamp is None else timestamp
        monotonic_now = (
            time.monotonic() if monotonic_timestamp is None else monotonic_timestamp
        )
        self._frame_index += 1
        height, width = frame_shape[:2]
        frame_diagonal = math.hypot(width, height)

        roi_px = normalized_to_pixels(self.config.roi, width, height)
        legacy_polygons = {
            zone.name: normalized_to_pixels(zone.polygon, width, height)
            for zone in self.config.zones
        }
        restricted_polygons = {
            zone.name: normalized_to_pixels(zone.polygon, width, height)
            for zone in self.config.restricted_zones
        }
        crowd_polygons = {
            zone.name: normalized_to_pixels(zone.polygon, width, height)
            for zone in self.config.crowd_zones
        }
        train_polygon = normalized_to_pixels(
            self.config.train.polygon, width, height
        )
        litter_polygon = normalized_to_pixels(
            self.config.litter.polygon, width, height
        )
        dangerous_polygon = normalized_to_pixels(
            self.config.dangerous_objects.polygon, width, height
        )
        vandalism_polygon = normalized_to_pixels(
            self.config.vandalism.polygon, width, height
        )
        fall_polygon = normalized_to_pixels(
            self.config.fall_on_tracks.polygon, width, height
        )
        line_pixels = {
            line.name: normalized_line_to_pixels(line.line, width, height)
            for line in self.config.line_crossings
        }

        accepted: list[tuple[Detection, PointPx]] = []
        objects: dict[str, int] = {}
        for detection in detections:
            point = self._reference_point(detection)
            if not point_in_polygon(point, roi_px):
                continue
            accepted.append((detection, point))
            objects[detection.class_name] = objects.get(detection.class_name, 0) + 1

            state = self._tracks.get(detection.track_id)
            if state is None:
                state = TrackState(
                    history=deque(),
                    last_seen=monotonic_now,
                    bbox=detection.bbox,
                    confidence=detection.confidence,
                    class_id=detection.class_id,
                    class_name=detection.class_name,
                )
                self._tracks[detection.track_id] = state
            state.history.append((monotonic_now, point))
            history_cutoff = monotonic_now - self._analytics_history_s
            # Keep one sample immediately before the cutoff so time-window
            # rules can bridge the threshold instead of depending on exact
            # frame timestamps.
            while len(state.history) > 2 and state.history[1][0] < history_cutoff:
                state.history.popleft()
            state.last_seen = monotonic_now
            state.bbox = detection.bbox
            state.confidence = detection.confidence
            state.class_id = detection.class_id
            state.class_name = detection.class_name

        persons = [
            item for item in accepted if item[0].class_id in self.config.person_class_ids
        ]
        events: list[AnalyticsEvent] = []
        snapshots: list[ZoneSnapshot] = []

        # Train presence is fail-safe. It starts UNKNOWN and changes only after
        # a stable positive/negative observation inside the calibrated tracks
        # polygon. UNKNOWN never authorizes a yellow-line safety event.
        if self.config.train.enabled and train_polygon.size:
            train_detected = any(
                detection.class_id in self.config.train.class_ids
                and point_in_polygon(point, train_polygon)
                for detection, point in accepted
            )
            candidate = "PRESENT" if train_detected else "ABSENT"
            if self._train_state.candidate != candidate:
                self._train_state.candidate = candidate
                self._train_state.candidate_since = monotonic_now
            confirm_s = (
                self.config.train.present_confirm_s
                if candidate == "PRESENT"
                else self.config.train.absent_confirm_s
            )
            if (
                self._train_state.value != candidate
                and monotonic_now - self._train_state.candidate_since >= confirm_s
            ):
                previous = self._train_state.value
                self._train_state.value = candidate
                events.append(
                    self._event(
                        event_type="train_state_changed",
                        timestamp=now,
                        severity="info",
                        zone="tracks",
                        object_class="train" if candidate == "PRESENT" else None,
                        details={"previous": previous, "current": candidate},
                    )
                )
        else:
            self._train_state = TrainState()
        train_state = self._train_state.value

        # Legacy directional polygon analytics. Stationary tracks are now neutral
        # and a track can be counted again only after leaving and re-entering.
        for zone in self.config.zones:
            polygon = legacy_polygons[zone.name]
            zone_people = 0
            stationary = 0
            live = {
                zone.direction_labels[0]: 0,
                zone.direction_labels[1]: 0,
            }
            for detection, point in persons:
                key = (zone.name, detection.track_id)
                zstate = self._zone_states.setdefault(key, ZoneTrackState())
                zstate.last_seen = monotonic_now
                inside = point_in_polygon(point, polygon)
                if not inside:
                    zstate.seen_inside = False
                    zstate.counted = False
                    continue

                zone_people += 1
                zstate.seen_inside = True
                track = self._tracks[detection.track_id]
                delta = self._axis_delta(
                    track.history,
                    zone.direction_axis,
                    width,
                    height,
                    min(zone.min_history, len(track.history)),
                )
                if abs(delta) <= zone.stationary_deadband:
                    stationary += 1
                else:
                    live_direction = (
                        zone.direction_labels[0]
                        if delta > 0
                        else zone.direction_labels[1]
                    )
                    live[live_direction] += 1

                if zstate.counted or len(track.history) < zone.min_history:
                    continue
                exact_delta = self._axis_delta(
                    track.history,
                    zone.direction_axis,
                    width,
                    height,
                    zone.min_history,
                )
                if abs(exact_delta) < zone.min_displacement:
                    continue
                direction = (
                    zone.direction_labels[0]
                    if exact_delta > 0
                    else zone.direction_labels[1]
                )
                zstate.counted = True
                self._cumulative[zone.name][direction] += 1
                events.append(
                    self._event(
                        event_type="legacy_direction",
                        timestamp=now,
                        severity="info",
                        track_id=detection.track_id,
                        zone=zone.name,
                        direction=direction,
                        object_class=detection.class_name,
                    )
                )

            snapshots.append(
                ZoneSnapshot(
                    name=zone.name,
                    kind="directional",
                    people=zone_people,
                    density_people_m2=(
                        None
                        if zone.area_m2 in (None, 0)
                        else zone_people / zone.area_m2
                    ),
                    level=None,
                    polygon_px=polygon,
                    color=zone.color,
                    live_directions=live,
                    cumulative_directions=dict(self._cumulative[zone.name]),
                    stationary=stationary,
                )
            )

        # Finite virtual-line crossing. A side change alone is not enough: the
        # track segment must intersect the configured line segment.
        for line in self.config.line_crossings:
            line_start, line_end = line_pixels[line.name]
            for detection, point in accepted:
                if detection.class_id not in line.class_ids:
                    continue
                key = (line.name, detection.track_id)
                state = self._line_states.setdefault(key, LineTrackState())
                state.last_seen = monotonic_now
                signed = signed_distance_to_line(point, line_start, line_end)
                normalized_signed = signed / max(frame_diagonal, 1.0)
                current_side = (
                    0
                    if abs(normalized_signed) <= line.hysteresis
                    else (1 if normalized_signed > 0 else -1)
                )
                if current_side == 0:
                    continue

                if (
                    state.last_side != 0
                    and state.last_side != current_side
                    and state.last_side_point is not None
                    and segments_intersect(
                        state.last_side_point, point, line_start, line_end
                    )
                    and monotonic_now - state.last_crossing_at >= line.cooldown_s
                ):
                    direction = (
                        line.direction_labels[0]
                        if state.last_side < current_side
                        else line.direction_labels[1]
                    )
                    severity = (
                        "critical"
                        if line.prohibited_direction == direction
                        else "info"
                    )
                    prohibited = line.prohibited_direction == direction
                    guarded = prohibited and line.require_train_absent
                    authorized = not guarded or train_state == "ABSENT"
                    events.append(
                        self._event(
                            event_type=(
                                "line_crossing"
                                if authorized
                                else "yellow_line_crossing_suppressed"
                            ),
                            timestamp=now,
                            severity=severity if authorized else "warning",
                            track_id=detection.track_id,
                            zone=line.name,
                            direction=direction,
                            object_class=detection.class_name,
                            details={
                                "prohibited": prohibited,
                                "detector_confidence": round(detection.confidence, 5),
                                "train_state": train_state,
                                "suppressed": not authorized,
                                "reason": (
                                    None
                                    if authorized
                                    else "train_not_confirmed_absent"
                                ),
                            },
                        )
                    )
                    state.last_crossing_at = monotonic_now

                state.last_side = current_side
                state.last_side_point = point

        # Restricted/off-limits polygons. Entry is stateful and optionally has a
        # grace period to absorb one-frame detector jitter.
        for zone in self.config.restricted_zones:
            polygon = restricted_polygons[zone.name]
            people_inside = 0
            for detection, point in accepted:
                if detection.class_id not in zone.class_ids:
                    continue
                key = (zone.name, detection.track_id)
                state = self._restricted_states.setdefault(
                    key, RestrictedTrackState()
                )
                state.last_seen = monotonic_now
                inside = point_in_polygon(point, polygon)
                if not inside:
                    state.inside = False
                    state.entered_at = None
                    continue

                people_inside += 1
                if not state.inside:
                    state.inside = True
                    state.entered_at = monotonic_now

                entered_at = state.entered_at or monotonic_now
                grace_elapsed = monotonic_now - entered_at >= zone.entry_grace_s
                repeat_ready = (
                    monotonic_now - state.last_alert_at >= zone.repeat_interval_s
                )
                if grace_elapsed and repeat_ready:
                    events.append(
                        self._event(
                            event_type="restricted_zone_entry",
                            timestamp=now,
                            severity=zone.severity,
                            track_id=detection.track_id,
                            zone=zone.name,
                            object_class=detection.class_name,
                            details={
                                "inside_for_s": round(monotonic_now - entered_at, 3)
                            },
                        )
                    )
                    state.last_alert_at = monotonic_now

            snapshots.append(
                ZoneSnapshot(
                    name=zone.name,
                    kind="restricted",
                    people=people_inside,
                    density_people_m2=None,
                    level="alert" if people_inside else "normal",
                    polygon_px=polygon,
                    color=zone.color,
                )
            )

        # Crowd density zones with stable threshold transitions.
        for zone in self.config.crowd_zones:
            polygon = crowd_polygons[zone.name]
            people_inside = sum(
                1 for _, point in persons if point_in_polygon(point, polygon)
            )
            density = (
                None
                if zone.area_m2 in (None, 0)
                else people_inside / zone.area_m2
            )
            level = self._density_level(
                density, zone.warning_density, zone.critical_density
            )
            state = self._crowd_states.setdefault(zone.name, CrowdAlertState())
            resolved_level = level or "normal"
            if state.candidate_level != resolved_level:
                state.candidate_level = resolved_level
                state.candidate_since = monotonic_now
            stable = monotonic_now - state.candidate_since >= zone.hold_s
            if stable and state.active_level != resolved_level:
                previous_level = state.active_level
                state.active_level = resolved_level
                if resolved_level in {"warning", "critical"}:
                    is_escalation = (
                        resolved_level == "critical" and previous_level != "critical"
                    )
                    cooldown_ready = (
                        monotonic_now - state.last_alert_at >= zone.cooldown_s
                    )
                    if is_escalation or cooldown_ready:
                        events.append(
                            self._event(
                                event_type="crowd_density",
                                timestamp=now,
                                severity=resolved_level,
                                zone=zone.name,
                                details={
                                    "people": people_inside,
                                    "density_people_m2": density,
                                    "mean_person_confidence": (
                                        None
                                        if people_inside == 0
                                        else round(
                                            sum(
                                                person.confidence
                                                for person, point in persons
                                                if point_in_polygon(point, polygon)
                                            ) / people_inside,
                                            5,
                                        )
                                    ),
                                    "previous_level": previous_level,
                                },
                            )
                        )
                        state.last_alert_at = monotonic_now

            snapshots.append(
                ZoneSnapshot(
                    name=zone.name,
                    kind="crowd",
                    people=people_inside,
                    density_people_m2=density,
                    level=level,
                    polygon_px=polygon,
                    color=zone.color,
                )
            )

        luggage_associations: list[LuggageAssociationView] = []

        # Associate a specific owner with each luggage track. Initial ownership
        # must persist for a short confirmation interval, and a short owner-ID
        # switch can be recovered only near the owner's last known position.
        # This avoids replacing the owner with an arbitrary passer-by near the
        # luggage while still tolerating brief tracker ID changes/occlusions.
        if self.config.luggage.enabled:
            luggage_persons = [
                item
                for item in accepted
                if item[0].class_id in self.config.luggage.person_class_ids
            ]
            for detection, _ in accepted:
                if detection.class_id not in self.config.luggage.object_class_ids:
                    continue
                track = self._tracks[detection.track_id]
                state = self._luggage_states.setdefault(
                    detection.track_id, LuggageTrackState()
                )
                state.last_seen = monotonic_now
                stationary, motion_norm = self._is_stationary(
                    track,
                    monotonic_now,
                    frame_diagonal,
                    self.config.luggage.stationary_s,
                    self.config.luggage.max_motion_norm,
                )
                center = self._bbox_center(detection.bbox)
                nearest_id, nearest_distance = self._nearest_person(
                    center, luggage_persons, frame_diagonal
                )

                if state.owner_track_id is None:
                    initial_candidate = (
                        nearest_id
                        if nearest_distance is not None
                        and nearest_distance
                        <= self.config.luggage.association_distance_norm
                        else None
                    )
                    if self._stable_candidate(
                        state,
                        initial_candidate,
                        monotonic_now,
                        self.config.luggage.association_confirm_s,
                    ):
                        state.owner_track_id = initial_candidate
                        state.owner_last_seen = monotonic_now
                        owner_detection = next(
                            (
                                person
                                for person, _ in luggage_persons
                                if person.track_id == initial_candidate
                            ),
                            None,
                        )
                        if owner_detection is not None:
                            state.owner_last_position = self._bbox_center(
                                owner_detection.bbox
                            )
                        state.candidate_track_id = None
                        state.candidate_since = None

                owner_distance: float | None = None
                if state.owner_track_id is not None:
                    owner = next(
                        (
                            person
                            for person, _ in luggage_persons
                            if person.track_id == state.owner_track_id
                        ),
                        None,
                    )
                    if owner is not None:
                        state.owner_last_seen = monotonic_now
                        state.owner_last_position = self._bbox_center(owner.bbox)
                        state.reassociation_candidate_id = None
                        state.reassociation_candidate_since = None
                        owner_distance = (
                            euclidean_distance(
                                center, self._bbox_center(owner.bbox)
                            )
                            / max(frame_diagonal, 1.0)
                        )
                    elif (
                        state.owner_last_seen is not None
                        and state.owner_last_position is not None
                        and monotonic_now - state.owner_last_seen
                        <= self.config.luggage.owner_reassociation_window_s
                    ):
                        switch_id, switch_distance = self._nearest_person_to_point(
                            state.owner_last_position,
                            luggage_persons,
                            frame_diagonal,
                        )
                        switch_candidate = (
                            switch_id
                            if switch_id is not None
                            and switch_id != state.owner_track_id
                            and switch_distance is not None
                            and switch_distance
                            <= self.config.luggage.owner_reassociation_distance_norm
                            else None
                        )
                        if self._stable_candidate(
                            state,
                            switch_candidate,
                            monotonic_now,
                            self.config.luggage.owner_reassociation_confirm_s,
                            reassociation=True,
                        ):
                            state.owner_track_id = switch_candidate
                            state.owner_last_seen = monotonic_now
                            state.owner_switches += 1
                            switched = next(
                                (
                                    person
                                    for person, _ in luggage_persons
                                    if person.track_id == switch_candidate
                                ),
                                None,
                            )
                            if switched is not None:
                                state.owner_last_position = self._bbox_center(
                                    switched.bbox
                                )
                                owner_distance = (
                                    euclidean_distance(
                                        center, state.owner_last_position
                                    )
                                    / max(frame_diagonal, 1.0)
                                )
                            state.reassociation_candidate_id = None
                            state.reassociation_candidate_since = None

                if state.owner_track_id is not None:
                    owner_missing_for = (
                        math.inf
                        if state.owner_last_seen is None
                        else monotonic_now - state.owner_last_seen
                    )
                    separated = (
                        owner_distance is not None
                        and owner_distance > self.config.luggage.owner_distance_norm
                    ) or (
                        owner_distance is None
                        and owner_missing_for
                        >= self.config.luggage.owner_missing_grace_s
                    )
                else:
                    separated = (
                        not self.config.luggage.require_owner_association
                        and (
                            nearest_distance is None
                            or nearest_distance
                            > self.config.luggage.owner_distance_norm
                        )
                    )
                case = (
                    "owner_separated"
                    if state.owner_track_id is not None
                    else "initially_unassociated"
                )
                unattended = stationary and separated
                if not unattended:
                    state.unattended_since = None
                    state.episode_id = None
                    state.alerted = False
                    unattended_for = 0.0
                else:
                    if state.unattended_since is None:
                        state.unattended_since = monotonic_now
                        state.episode_id = str(uuid.uuid4())
                    unattended_for = monotonic_now - state.unattended_since
                cooldown_ready = (
                    monotonic_now - state.last_alert_at
                    >= self.config.luggage.cooldown_s
                )
                if (
                    unattended
                    and
                    unattended_for >= self.config.luggage.unattended_s
                    and not state.alerted
                    and cooldown_ready
                ):
                    events.append(
                        self._event(
                            event_type="unattended_luggage",
                            timestamp=now,
                            severity="critical",
                            track_id=detection.track_id,
                            object_class=detection.class_name,
                            details={
                                "unattended_for_s": round(unattended_for, 3),
                                "detector_confidence": round(detection.confidence, 5),
                                "motion_norm": round(motion_norm, 5),
                                "owner_track_id": state.owner_track_id,
                                "owner_distance_norm": (
                                    None
                                    if owner_distance is None
                                    else round(owner_distance, 5)
                                ),
                                "owner_association_required": (
                                    self.config.luggage.require_owner_association
                                ),
                                "case": case,
                                "episode_id": state.episode_id,
                                "owner_switches": state.owner_switches,
                            },
                        )
                    )
                    state.alerted = True
                    state.last_alert_at = monotonic_now

                if unattended:
                    status = (
                        "alerted"
                        if state.alerted
                        else "unattended_pending"
                    )
                elif state.owner_track_id is not None:
                    owner_missing_for = (
                        math.inf
                        if state.owner_last_seen is None
                        else monotonic_now - state.owner_last_seen
                    )
                    status = (
                        "owner_missing_grace"
                        if owner_distance is None
                        and owner_missing_for
                        < self.config.luggage.owner_missing_grace_s
                        else "associated"
                    )
                elif state.candidate_track_id is not None:
                    status = "candidate"
                else:
                    status = "unassociated"
                luggage_associations.append(
                    LuggageAssociationView(
                        luggage_track_id=detection.track_id,
                        owner_track_id=state.owner_track_id,
                        candidate_track_id=(
                            state.reassociation_candidate_id
                            if state.reassociation_candidate_id is not None
                            else state.candidate_track_id
                        ),
                        status=status,
                        case=case,
                        owner_distance_norm=(
                            None
                            if owner_distance is None
                            else round(owner_distance, 5)
                        ),
                        unattended_for_s=round(unattended_for, 3),
                    )
                )

        # Animal supervision mirrors the luggage ownership strategy, but does
        # not require the animal to be stationary. A nearby person must persist
        # for a short confirmation interval before becoming the associated
        # supervisor; brief owner ID switches are recovered only near the last
        # known owner position. This avoids assigning a random passer-by.
        if self.config.animal.enabled:
            for detection, _ in accepted:
                if detection.class_id not in self.config.animal.animal_class_ids:
                    continue
                center = self._bbox_center(detection.bbox)
                state = self._animal_states.setdefault(
                    detection.track_id, AssociationTrackState()
                )
                state.last_seen = monotonic_now
                nearest_id, nearest_distance = self._nearest_person(
                    center, persons, frame_diagonal
                )

                # Establish the initial supervisor only after a stable nearby
                # candidate. A lone animal can still become an alert when
                # require_owner_association is false.
                if state.owner_track_id is None:
                    candidate = (
                        nearest_id
                        if nearest_id is not None
                        and nearest_distance is not None
                        and nearest_distance
                        <= self.config.animal.association_distance_norm
                        else None
                    )
                    if self._stable_candidate(
                        state,
                        candidate,
                        monotonic_now,
                        self.config.animal.association_confirm_s,
                    ):
                        state.owner_track_id = candidate
                        state.owner_last_seen = monotonic_now
                        state.candidate_track_id = None
                        state.candidate_since = None
                        owner = next(
                            (
                                person
                                for person, _ in persons
                                if person.track_id == state.owner_track_id
                            ),
                            None,
                        )
                        if owner is not None:
                            state.owner_last_position = self._bbox_center(owner.bbox)

                owner_distance: float | None = None
                owner = None
                if state.owner_track_id is not None:
                    owner = next(
                        (
                            person
                            for person, _ in persons
                            if person.track_id == state.owner_track_id
                        ),
                        None,
                    )
                    if owner is not None:
                        state.owner_last_seen = monotonic_now
                        state.owner_last_position = self._bbox_center(owner.bbox)
                        owner_distance = (
                            euclidean_distance(center, state.owner_last_position)
                            / max(frame_diagonal, 1.0)
                        )
                        state.reassociation_candidate_id = None
                        state.reassociation_candidate_since = None
                    else:
                        missing_for = (
                            math.inf
                            if state.owner_last_seen is None
                            else monotonic_now - state.owner_last_seen
                        )
                        # Only attempt an ID-switch recovery for a short window
                        # and near the old owner position.
                        if (
                            state.owner_last_position is not None
                            and missing_for
                            <= self.config.animal.owner_reassociation_window_s
                        ):
                            reassoc_id, reassoc_distance = self._nearest_person_to_point(
                                state.owner_last_position, persons, frame_diagonal
                            )
                            candidate = (
                                reassoc_id
                                if reassoc_id is not None
                                and reassoc_distance is not None
                                and reassoc_distance
                                <= self.config.animal.owner_reassociation_distance_norm
                                else None
                            )
                            if self._stable_candidate(
                                state,
                                candidate,
                                monotonic_now,
                                self.config.animal.owner_reassociation_confirm_s,
                                reassociation=True,
                            ):
                                previous_owner = state.owner_track_id
                                state.owner_track_id = candidate
                                state.owner_switches += int(
                                    previous_owner is not None
                                    and candidate is not None
                                    and previous_owner != candidate
                                )
                                state.owner_last_seen = monotonic_now
                                owner = next(
                                    (
                                        person
                                        for person, _ in persons
                                        if person.track_id == state.owner_track_id
                                    ),
                                    None,
                                )
                                if owner is not None:
                                    state.owner_last_position = self._bbox_center(owner.bbox)
                                    owner_distance = (
                                        euclidean_distance(
                                            center, state.owner_last_position
                                        )
                                        / max(frame_diagonal, 1.0)
                                    )
                                state.reassociation_candidate_id = None
                                state.reassociation_candidate_since = None

                if state.owner_track_id is not None:
                    missing_for = (
                        math.inf
                        if state.owner_last_seen is None
                        else monotonic_now - state.owner_last_seen
                    )
                    unsupervised = (
                        owner_distance is not None
                        and owner_distance
                        > self.config.animal.supervision_distance_norm
                    ) or (
                        owner_distance is None
                        and missing_for >= self.config.animal.owner_missing_grace_s
                    )
                    case = "owner_separated"
                else:
                    unsupervised = (
                        not self.config.animal.require_owner_association
                        and (
                            nearest_distance is None
                            or nearest_distance
                            > self.config.animal.supervision_distance_norm
                        )
                    )
                    case = "initially_unassociated"

                if not unsupervised:
                    state.unsupervised_since = None
                    state.episode_id = None
                    state.alerted = False
                    continue
                if state.unsupervised_since is None:
                    state.unsupervised_since = monotonic_now
                    state.episode_id = str(uuid.uuid4())
                unsupervised_for = monotonic_now - state.unsupervised_since
                if (
                    unsupervised_for >= self.config.animal.unsupervised_s
                    and not state.alerted
                    and monotonic_now - state.last_alert_at
                    >= self.config.animal.cooldown_s
                ):
                    events.append(
                        self._event(
                            event_type="unsupervised_animal",
                            timestamp=now,
                            severity="warning",
                            track_id=detection.track_id,
                            object_class=detection.class_name,
                            details={
                                "owner_track_id": state.owner_track_id,
                                "unsupervised_for_s": round(unsupervised_for, 3),
                                "detector_confidence": round(
                                    detection.confidence, 5
                                ),
                                "owner_distance_norm": (
                                    None
                                    if owner_distance is None
                                    else round(owner_distance, 5)
                                ),
                                "owner_association_required": (
                                    self.config.animal.require_owner_association
                                ),
                                "case": case,
                                "episode_id": state.episode_id,
                                "owner_switches": state.owner_switches,
                            },
                        )
                    )
                    state.alerted = True
                    state.last_alert_at = monotonic_now

        # Persistent litter/degradation requires a detector class supplied by
        # the configured weights. Persistence and immobility prevent a single
        # noisy frame from becoming an alert.
        if self.config.litter.enabled:
            for detection, point in accepted:
                if (
                    detection.class_id not in self.config.litter.class_ids
                    or not self._inside_optional_polygon(point, litter_polygon)
                ):
                    continue
                track = self._tracks[detection.track_id]
                state = self._litter_states.setdefault(
                    detection.track_id, TimedAlertState()
                )
                state.last_seen = monotonic_now
                stationary, motion_norm = self._is_stationary(
                    track,
                    monotonic_now,
                    frame_diagonal,
                    self.config.litter.stationary_s,
                    self.config.litter.max_motion_norm,
                )
                if not stationary:
                    state.condition_since = None
                    state.alerted = False
                    continue
                if state.condition_since is None:
                    state.condition_since = monotonic_now
                persistent_for = monotonic_now - state.condition_since
                if (
                    persistent_for >= self.config.litter.persist_s
                    and not state.alerted
                    and monotonic_now - state.last_alert_at
                    >= self.config.litter.cooldown_s
                ):
                    events.append(
                        self._event(
                            event_type="dirt_detected",
                            timestamp=now,
                            severity="warning",
                            track_id=detection.track_id,
                            object_class=detection.class_name,
                            details={
                                "persistent_for_s": round(persistent_for, 3),
                                "motion_norm": round(motion_norm, 5),
                            },
                        )
                    )
                    state.alerted = True
                    state.last_alert_at = monotonic_now

        if self.config.dangerous_objects.enabled:
            for detection, point in accepted:
                if (
                    detection.class_id
                    not in self.config.dangerous_objects.class_ids
                    or not self._inside_optional_polygon(point, dangerous_polygon)
                ):
                    continue
                state = self._danger_states.setdefault(
                    detection.track_id, TimedAlertState()
                )
                state.last_seen = monotonic_now
                if state.condition_since is None:
                    state.condition_since = monotonic_now
                visible_for = monotonic_now - state.condition_since
                if (
                    visible_for >= self.config.dangerous_objects.confirm_s
                    and not state.alerted
                    and monotonic_now - state.last_alert_at
                    >= self.config.dangerous_objects.cooldown_s
                ):
                    events.append(
                        self._event(
                            event_type="dangerous_object_detected",
                            timestamp=now,
                            severity="critical",
                            track_id=detection.track_id,
                            object_class=detection.class_name,
                            details={"confirmed_for_s": round(visible_for, 3)},
                        )
                    )
                    state.alerted = True
                    state.last_alert_at = monotonic_now

        if self.config.vandalism.enabled:
            for detection, point in accepted:
                if (
                    detection.class_id not in self.config.vandalism.class_ids
                    or not self._inside_optional_polygon(point, vandalism_polygon)
                ):
                    continue
                state = self._vandalism_states.setdefault(
                    detection.track_id, TimedAlertState()
                )
                state.last_seen = monotonic_now
                if state.condition_since is None:
                    state.condition_since = monotonic_now
                action_for = monotonic_now - state.condition_since
                if (
                    action_for >= self.config.vandalism.confirm_s
                    and not state.alerted
                    and monotonic_now - state.last_alert_at
                    >= self.config.vandalism.cooldown_s
                ):
                    events.append(
                        self._event(
                            event_type="vandalism_detected",
                            timestamp=now,
                            severity="critical",
                            track_id=detection.track_id,
                            object_class=detection.class_name,
                            details={"confirmed_for_s": round(action_for, 3)},
                        )
                    )
                    state.alerted = True
                    state.last_alert_at = monotonic_now

        # Conservative geometric fall baseline. Production accuracy requires a
        # pose/action model; this rule needs both a vertical drop and a stable
        # horizontal body shape inside the tracks polygon.
        if self.config.fall_on_tracks.enabled:
            for detection, point in persons:
                if (
                    detection.class_id
                    not in self.config.fall_on_tracks.person_class_ids
                    or not point_in_polygon(point, fall_polygon)
                ):
                    continue
                x1, y1, x2, y2 = detection.bbox
                aspect_ratio = (x2 - x1) / max(y2 - y1, 1)
                track = self._tracks[detection.track_id]
                history_points = self._history_points(track.history)
                vertical_drop_norm = (
                    point[1] - min(item[1] for item in history_points)
                ) / max(height, 1)
                condition = (
                    aspect_ratio >= self.config.fall_on_tracks.horizontal_ratio
                    and vertical_drop_norm
                    >= self.config.fall_on_tracks.min_vertical_drop_norm
                )
                state = self._fall_states.setdefault(
                    detection.track_id, TimedAlertState()
                )
                state.last_seen = monotonic_now
                if not condition:
                    state.condition_since = None
                    state.alerted = False
                    continue
                if state.condition_since is None:
                    state.condition_since = monotonic_now
                fallen_for = monotonic_now - state.condition_since
                if (
                    fallen_for >= self.config.fall_on_tracks.confirm_s
                    and not state.alerted
                    and monotonic_now - state.last_alert_at
                    >= self.config.fall_on_tracks.cooldown_s
                ):
                    events.append(
                        self._event(
                            event_type="fall_on_tracks",
                            timestamp=now,
                            severity="critical",
                            track_id=detection.track_id,
                            zone="tracks",
                            object_class=detection.class_name,
                            details={
                                "fallen_for_s": round(fallen_for, 3),
                                "aspect_ratio": round(aspect_ratio, 4),
                                "vertical_drop_norm": round(
                                    vertical_drop_norm, 5
                                ),
                                "baseline": "bbox_motion",
                            },
                        )
                    )
                    state.alerted = True
                    state.last_alert_at = monotonic_now

        # Remove stale state so long-running processes remain memory bounded.
        stale_track_ids = [
            track_id
            for track_id, state in self._tracks.items()
            if monotonic_now - state.last_seen > self.config.track_ttl_s
        ]
        for track_id in stale_track_ids:
            self._tracks.pop(track_id, None)
            self._luggage_states.pop(track_id, None)
            self._animal_states.pop(track_id, None)
            self._litter_states.pop(track_id, None)
            self._danger_states.pop(track_id, None)
            self._vandalism_states.pop(track_id, None)
            self._fall_states.pop(track_id, None)

        def stale(mapping: dict[Any, Any]) -> list[Any]:
            return [
                key
                for key, state in mapping.items()
                if monotonic_now - state.last_seen > self.config.track_ttl_s
            ]

        for mapping in (
            self._zone_states,
            self._line_states,
            self._restricted_states,
        ):
            for key in stale(mapping):
                mapping.pop(key, None)

        track_views = tuple(
            TrackView(
                track_id=detection.track_id,
                class_id=detection.class_id,
                class_name=detection.class_name,
                bbox=detection.bbox,
                confidence=detection.confidence,
                point=point,
                history=tuple(
                    self._history_points(self._tracks[detection.track_id].history)[
                        -max(2, self.config.tail_length) :
                    ]
                ),
            )
            for detection, point in accepted
            if detection.track_id in self._tracks
        )
        line_snapshots = tuple(
            LineSnapshot(
                name=line.name,
                start=line_pixels[line.name][0],
                end=line_pixels[line.name][1],
                color=line.color,
            )
            for line in self.config.line_crossings
        )

        return AnalysisResult(
            frame_index=self._frame_index,
            timestamp=now,
            people=len(persons),
            objects=objects,
            train_state=train_state,
            density_people_m2=(
                None
                if self.config.scene_area_m2 in (None, 0)
                else len(persons) / self.config.scene_area_m2
            ),
            zones=tuple(snapshots),
            lines=line_snapshots,
            tracks=track_views,
            luggage_associations=tuple(luggage_associations),
            events=tuple(events),
            roi_px=roi_px,
        )
