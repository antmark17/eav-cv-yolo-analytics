from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import os

import yaml

PointNorm = tuple[float, float]


def _as_points(value: Any) -> list[PointNorm]:
    """Convert a nullable YAML polygon to normalized points.

    ``null`` and an empty list both mean that the polygon is disabled. This is
    useful while ROI and zones are being calibrated manually.
    """
    if value in (None, []):
        return []
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"A polygon must be a list of points, got {value!r}")

    points: list[PointNorm] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(f"Invalid point: {item!r}")
        x, y = float(item[0]), float(item[1])
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError(
                f"Normalized coordinates must be in [0, 1], got {(x, y)}"
            )
        points.append((x, y))
    if points and len(points) < 3:
        raise ValueError("A polygon must contain at least 3 points")
    return points


def _as_line(value: Any) -> tuple[PointNorm, PointNorm]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("A line must contain exactly two normalized points")
    points: list[PointNorm] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(f"Invalid line point: {item!r}")
        x, y = float(item[0]), float(item[1])
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError(
                f"Normalized coordinates must be in [0, 1], got {(x, y)}"
            )
        points.append((x, y))
    if points[0] == points[1]:
        raise ValueError("A line cannot have identical endpoints")
    return points[0], points[1]


def _as_color(value: Any, default: tuple[int, int, int]) -> tuple[int, int, int]:
    if value is None:
        return default
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"A BGR color must have three values, got {value!r}")
    color = tuple(int(v) for v in value)
    if any(v < 0 or v > 255 for v in color):
        raise ValueError(f"Color values must be in [0, 255], got {color}")
    return color


def _as_int_list(value: Any, default: list[int]) -> list[int]:
    if value in (None, []):
        return list(default)
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"Expected a list of class IDs, got {value!r}")
    return [int(item) for item in value]


@dataclass(slots=True)
class SourceConfig:
    uri: str | int
    mode: str = "stream"
    target_fps: float = 10.0
    snapshot_timeout_s: float = 5.0
    reconnect_delay_s: float = 3.0
    startup_timeout_s: float = 12.0
    open_timeout_ms: int = 8_000
    read_timeout_ms: int = 8_000
    loop_file: bool = False
    max_frame_age_s: float | None = 5.0
    youtube_max_height: int = 720
    youtube_cookies_from_browser: str | None = None


@dataclass(slots=True)
class ModelConfig:
    weights: str = "yolo12n.pt"
    device: str = "auto"
    confidence: float = 0.4
    iou: float = 0.5
    image_size: int = 640
    tracker: str = "bytetrack.yaml"
    # COCO baseline: person, train, animals, luggage, bat, knife and scissors.
    classes: list[int] = field(
        default_factory=lambda: [
            0,
            6,
            *range(14, 24),
            24,
            26,
            28,
            34,
            43,
            76,
        ]
    )
    # Ultralytics >=8.4 uses ``quantize`` for inference precision.
    # ``16`` selects FP16, while ``None``/``32`` keeps FP32.  The loader still
    # accepts the legacy YAML key ``half: true`` and maps it to ``16``.
    quantize: int | str | None = None


@dataclass(slots=True)
class ZoneConfig:
    """Legacy directional polygon, retained for backwards compatibility."""

    name: str
    polygon: list[PointNorm]
    direction_labels: tuple[str, str] = ("Positive", "Negative")
    direction_axis: str = "y"
    min_history: int = 8
    min_displacement: float = 0.04
    stationary_deadband: float = 0.01
    area_m2: float | None = None
    color: tuple[int, int, int] = (255, 165, 0)


@dataclass(slots=True)
class LineCrossingConfig:
    name: str
    line: tuple[PointNorm, PointNorm]
    direction_labels: tuple[str, str] = ("negative_to_positive", "positive_to_negative")
    class_ids: list[int] = field(default_factory=lambda: [0])
    cooldown_s: float = 2.0
    hysteresis: float = 0.006
    prohibited_direction: str | None = None
    require_train_absent: bool = False
    color: tuple[int, int, int] = (0, 0, 255)


@dataclass(slots=True)
class RestrictedZoneConfig:
    name: str
    polygon: list[PointNorm]
    class_ids: list[int] = field(default_factory=lambda: [0])
    entry_grace_s: float = 0.0
    repeat_interval_s: float = 30.0
    severity: str = "critical"
    color: tuple[int, int, int] = (0, 0, 255)


@dataclass(slots=True)
class CrowdZoneConfig:
    name: str
    polygon: list[PointNorm]
    area_m2: float | None = None
    warning_density: float | None = None
    critical_density: float | None = None
    hold_s: float = 3.0
    cooldown_s: float = 30.0
    color: tuple[int, int, int] = (0, 165, 255)


@dataclass(slots=True)
class LuggageConfig:
    enabled: bool = True
    person_class_ids: list[int] = field(default_factory=lambda: [0])
    object_class_ids: list[int] = field(default_factory=lambda: [24, 26, 28])
    stationary_s: float = 4.0
    unattended_s: float = 15.0
    max_motion_norm: float = 0.018
    association_distance_norm: float = 0.12
    association_confirm_s: float = 0.6
    owner_distance_norm: float = 0.16
    owner_missing_grace_s: float = 2.0
    owner_reassociation_window_s: float = 3.0
    owner_reassociation_distance_norm: float = 0.08
    owner_reassociation_confirm_s: float = 0.4
    require_owner_association: bool = True
    cooldown_s: float = 60.0


@dataclass(slots=True)
class TrainPresenceConfig:
    enabled: bool = False
    class_ids: list[int] = field(default_factory=lambda: [6])
    polygon: list[PointNorm] = field(default_factory=list)
    present_confirm_s: float = 0.5
    absent_confirm_s: float = 2.0


@dataclass(slots=True)
class AnimalSupervisionConfig:
    enabled: bool = False
    animal_class_ids: list[int] = field(default_factory=lambda: list(range(14, 24)))
    association_distance_norm: float = 0.18
    association_confirm_s: float = 0.6
    supervision_distance_norm: float = 0.24
    owner_missing_grace_s: float = 2.0
    owner_reassociation_window_s: float = 3.0
    owner_reassociation_distance_norm: float = 0.10
    owner_reassociation_confirm_s: float = 0.4
    unsupervised_s: float = 10.0
    require_owner_association: bool = True
    cooldown_s: float = 60.0


@dataclass(slots=True)
class LitterConfig:
    """Persistent litter/degradation detections from custom or selected classes."""

    enabled: bool = False
    class_ids: list[int] = field(default_factory=list)
    polygon: list[PointNorm] = field(default_factory=list)
    stationary_s: float = 3.0
    persist_s: float = 10.0
    max_motion_norm: float = 0.018
    cooldown_s: float = 60.0


@dataclass(slots=True)
class DangerousObjectConfig:
    enabled: bool = False
    # COCO baseline: baseball bat=34, knife=43, scissors=76.
    class_ids: list[int] = field(default_factory=lambda: [34, 43, 76])
    polygon: list[PointNorm] = field(default_factory=list)
    confirm_s: float = 0.5
    cooldown_s: float = 30.0


@dataclass(slots=True)
class VandalismConfig:
    """Temporal alert fed by vandalism/action classes from custom weights."""

    enabled: bool = False
    class_ids: list[int] = field(default_factory=list)
    polygon: list[PointNorm] = field(default_factory=list)
    confirm_s: float = 1.5
    cooldown_s: float = 60.0


@dataclass(slots=True)
class FallOnTracksConfig:
    enabled: bool = False
    polygon: list[PointNorm] = field(default_factory=list)
    person_class_ids: list[int] = field(default_factory=lambda: [0])
    horizontal_ratio: float = 1.15
    min_vertical_drop_norm: float = 0.06
    confirm_s: float = 1.0
    cooldown_s: float = 60.0


@dataclass(slots=True)
class HealthConfig:
    enabled: bool = True
    offline_after_s: float = 8.0
    black_luma_threshold: float = 5.0
    black_after_s: float = 3.0
    frozen_mean_delta: float = 0.35
    frozen_after_s: float = 10.0
    blur_variance_threshold: float = 4.0
    blur_after_s: float = 5.0
    low_fps_threshold: float = 1.0
    low_fps_after_s: float = 10.0
    cooldown_s: float = 60.0


@dataclass(slots=True)
class AnalyticsConfig:
    roi: list[PointNorm] = field(default_factory=list)
    zones: list[ZoneConfig] = field(default_factory=list)
    line_crossings: list[LineCrossingConfig] = field(default_factory=list)
    restricted_zones: list[RestrictedZoneConfig] = field(default_factory=list)
    crowd_zones: list[CrowdZoneConfig] = field(default_factory=list)
    luggage: LuggageConfig = field(default_factory=LuggageConfig)
    train: TrainPresenceConfig = field(default_factory=TrainPresenceConfig)
    animal: AnimalSupervisionConfig = field(default_factory=AnimalSupervisionConfig)
    litter: LitterConfig = field(default_factory=LitterConfig)
    dangerous_objects: DangerousObjectConfig = field(
        default_factory=DangerousObjectConfig
    )
    vandalism: VandalismConfig = field(default_factory=VandalismConfig)
    fall_on_tracks: FallOnTracksConfig = field(default_factory=FallOnTracksConfig)
    health: HealthConfig = field(default_factory=HealthConfig)
    person_class_ids: list[int] = field(default_factory=lambda: [0])
    tail_length: int = 30
    track_ttl_s: float = 2.5
    reference_point: str = "bottom_center"
    scene_area_m2: float | None = None


@dataclass(slots=True)
class OutputConfig:
    display: bool = True
    window_name: str = "EAV Smart Station Analytics"
    display_scale: float = 1.0
    video_path: str | None = None
    video_fps: float | None = None
    jsonl_path: str | None = None
    event_frames_dir: str | None = "outputs/event_frames"
    draw_tails: bool = True
    show_confidence: bool = True
    status_every_s: float = 2.0


@dataclass(slots=True)
class TeamBOutputConfig:
    """Local export settings for the strict Team B JSON contract.

    Network delivery is intentionally outside this configuration.  The
    pipeline writes validated JSON Lines files that can be inspected and
    replayed before an HTTP/MQTT transport is introduced.
    """

    enabled: bool = False
    platform_id: str | None = None
    specific_location: str | None = None
    source_device_id: str | None = None
    people_flow_every_s: float = 5.0
    people_flow_jsonl_path: str = "outputs/team_b_people_flow.jsonl"
    events_jsonl_path: str = "outputs/team_b_events.jsonl"
    event_id_db_path: str = "outputs/team_b_state.sqlite3"
    yellow_line_names: list[str] = field(default_factory=list)
    restricted_zone_names: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AppConfig:
    source: SourceConfig
    model: ModelConfig = field(default_factory=ModelConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    team_b: TeamBOutputConfig = field(default_factory=TeamBOutputConfig)


def _coerce_source_uri(value: Any) -> str | int:
    if isinstance(value, int):
        return value
    value = os.path.expandvars(str(value)).strip()
    if value.isdigit():
        return int(value)
    return value


def _nullable_float(value: Any) -> float | None:
    return None if value in (None, "") else float(value)


def _nullable_string(value: Any) -> str | None:
    if value is None:
        return None
    resolved = os.path.expandvars(str(value)).strip()
    return resolved or None


def _as_string_list(value: Any) -> list[str]:
    if value in (None, []):
        return []
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"Expected a list of strings, got {value!r}")
    result: list[str] = []
    for item in value:
        resolved = str(item).strip()
        if not resolved:
            raise ValueError("String lists cannot contain empty values")
        result.append(resolved)
    if len(result) != len(set(result)):
        raise ValueError("String lists cannot contain duplicate values")
    return result


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    src = raw.get("source", {}) or {}
    model = raw.get("model", {}) or {}
    analytics = raw.get("analytics", {}) or {}
    output = raw.get("output", {}) or {}
    team_b = raw.get("team_b", {}) or {}

    zones: list[ZoneConfig] = []
    for item in analytics.get("zones", []) or []:
        labels = item.get("direction_labels", ["Positive", "Negative"])
        if len(labels) != 2:
            raise ValueError("direction_labels must contain exactly two strings")
        axis = str(item.get("direction_axis", "y")).lower()
        if axis not in {"x", "y"}:
            raise ValueError("direction_axis must be 'x' or 'y'")
        zones.append(
            ZoneConfig(
                name=str(item["name"]),
                polygon=_as_points(item.get("polygon")),
                direction_labels=(str(labels[0]), str(labels[1])),
                direction_axis=axis,
                min_history=int(item.get("min_history", 8)),
                min_displacement=float(item.get("min_displacement", 0.04)),
                stationary_deadband=float(item.get("stationary_deadband", 0.01)),
                area_m2=_nullable_float(item.get("area_m2")),
                color=_as_color(item.get("color"), (255, 165, 0)),
            )
        )

    line_crossings: list[LineCrossingConfig] = []
    for item in analytics.get("line_crossings", []) or []:
        labels = item.get(
            "direction_labels", ["negative_to_positive", "positive_to_negative"]
        )
        if len(labels) != 2:
            raise ValueError("line crossing direction_labels must contain two strings")
        line_crossings.append(
            LineCrossingConfig(
                name=str(item["name"]),
                line=_as_line(item.get("line")),
                direction_labels=(str(labels[0]), str(labels[1])),
                class_ids=_as_int_list(item.get("class_ids"), [0]),
                cooldown_s=float(item.get("cooldown_s", 2.0)),
                hysteresis=float(item.get("hysteresis", 0.006)),
                prohibited_direction=(
                    None
                    if item.get("prohibited_direction") in (None, "")
                    else str(item["prohibited_direction"])
                ),
                require_train_absent=bool(
                    item.get("require_train_absent", False)
                ),
                color=_as_color(item.get("color"), (0, 0, 255)),
            )
        )

    restricted_zones: list[RestrictedZoneConfig] = []
    for item in analytics.get("restricted_zones", []) or []:
        restricted_zones.append(
            RestrictedZoneConfig(
                name=str(item["name"]),
                polygon=_as_points(item.get("polygon")),
                class_ids=_as_int_list(item.get("class_ids"), [0]),
                entry_grace_s=float(item.get("entry_grace_s", 0.0)),
                repeat_interval_s=float(item.get("repeat_interval_s", 30.0)),
                severity=str(item.get("severity", "critical")),
                color=_as_color(item.get("color"), (0, 0, 255)),
            )
        )

    crowd_zones: list[CrowdZoneConfig] = []
    for item in analytics.get("crowd_zones", []) or []:
        crowd_zones.append(
            CrowdZoneConfig(
                name=str(item["name"]),
                polygon=_as_points(item.get("polygon")),
                area_m2=_nullable_float(item.get("area_m2")),
                warning_density=_nullable_float(item.get("warning_density")),
                critical_density=_nullable_float(item.get("critical_density")),
                hold_s=float(item.get("hold_s", 3.0)),
                cooldown_s=float(item.get("cooldown_s", 30.0)),
                color=_as_color(item.get("color"), (0, 165, 255)),
            )
        )

    luggage_raw = analytics.get("luggage", {}) or {}
    luggage = LuggageConfig(
        enabled=bool(luggage_raw.get("enabled", True)),
        person_class_ids=_as_int_list(luggage_raw.get("person_class_ids"), [0]),
        object_class_ids=_as_int_list(
            luggage_raw.get("object_class_ids"), [24, 26, 28]
        ),
        stationary_s=float(luggage_raw.get("stationary_s", 4.0)),
        unattended_s=float(luggage_raw.get("unattended_s", 15.0)),
        max_motion_norm=float(luggage_raw.get("max_motion_norm", 0.018)),
        association_distance_norm=float(
            luggage_raw.get("association_distance_norm", 0.12)
        ),
        association_confirm_s=float(
            luggage_raw.get("association_confirm_s", 0.6)
        ),
        owner_distance_norm=float(
            luggage_raw.get("owner_distance_norm", 0.16)
        ),
        owner_missing_grace_s=float(
            luggage_raw.get("owner_missing_grace_s", 2.0)
        ),
        owner_reassociation_window_s=float(
            luggage_raw.get("owner_reassociation_window_s", 3.0)
        ),
        owner_reassociation_distance_norm=float(
            luggage_raw.get("owner_reassociation_distance_norm", 0.08)
        ),
        owner_reassociation_confirm_s=float(
            luggage_raw.get("owner_reassociation_confirm_s", 0.4)
        ),
        require_owner_association=bool(
            luggage_raw.get("require_owner_association", True)
        ),
        cooldown_s=float(luggage_raw.get("cooldown_s", 60.0)),
    )
    for name, value in (
        ("association_confirm_s", luggage.association_confirm_s),
        ("owner_missing_grace_s", luggage.owner_missing_grace_s),
        ("owner_reassociation_window_s", luggage.owner_reassociation_window_s),
        ("owner_reassociation_confirm_s", luggage.owner_reassociation_confirm_s),
        ("stationary_s", luggage.stationary_s),
        ("unattended_s", luggage.unattended_s),
    ):
        if value < 0:
            raise ValueError(f"analytics.luggage.{name} cannot be negative")

    train_raw = analytics.get("train", {}) or {}
    train = TrainPresenceConfig(
        enabled=bool(train_raw.get("enabled", False)),
        class_ids=_as_int_list(train_raw.get("class_ids"), [6]),
        polygon=_as_points(train_raw.get("polygon")),
        present_confirm_s=float(train_raw.get("present_confirm_s", 0.5)),
        absent_confirm_s=float(train_raw.get("absent_confirm_s", 2.0)),
    )

    animal_raw = analytics.get("animal", {}) or {}
    animal = AnimalSupervisionConfig(
        enabled=bool(animal_raw.get("enabled", False)),
        animal_class_ids=_as_int_list(
            animal_raw.get("animal_class_ids"), list(range(14, 24))
        ),
        association_distance_norm=float(
            animal_raw.get("association_distance_norm", 0.18)
        ),
        association_confirm_s=float(
            animal_raw.get("association_confirm_s", 0.6)
        ),
        supervision_distance_norm=float(
            animal_raw.get("supervision_distance_norm", 0.24)
        ),
        owner_missing_grace_s=float(
            animal_raw.get("owner_missing_grace_s", 2.0)
        ),
        owner_reassociation_window_s=float(
            animal_raw.get("owner_reassociation_window_s", 3.0)
        ),
        owner_reassociation_distance_norm=float(
            animal_raw.get("owner_reassociation_distance_norm", 0.10)
        ),
        owner_reassociation_confirm_s=float(
            animal_raw.get("owner_reassociation_confirm_s", 0.4)
        ),
        unsupervised_s=float(animal_raw.get("unsupervised_s", 10.0)),
        require_owner_association=bool(
            animal_raw.get("require_owner_association", True)
        ),
        cooldown_s=float(animal_raw.get("cooldown_s", 60.0)),
    )

    for name, value in (
        ("association_confirm_s", animal.association_confirm_s),
        ("owner_missing_grace_s", animal.owner_missing_grace_s),
        ("owner_reassociation_window_s", animal.owner_reassociation_window_s),
        ("owner_reassociation_confirm_s", animal.owner_reassociation_confirm_s),
        ("unsupervised_s", animal.unsupervised_s),
    ):
        if value < 0:
            raise ValueError(f"analytics.animal.{name} cannot be negative")

    litter_raw = analytics.get("litter", {}) or {}
    litter = LitterConfig(
        enabled=bool(litter_raw.get("enabled", False)),
        class_ids=_as_int_list(litter_raw.get("class_ids"), []),
        polygon=_as_points(litter_raw.get("polygon")),
        stationary_s=float(litter_raw.get("stationary_s", 3.0)),
        persist_s=float(litter_raw.get("persist_s", 10.0)),
        max_motion_norm=float(litter_raw.get("max_motion_norm", 0.018)),
        cooldown_s=float(litter_raw.get("cooldown_s", 60.0)),
    )

    dangerous_raw = analytics.get("dangerous_objects", {}) or {}
    dangerous_objects = DangerousObjectConfig(
        enabled=bool(dangerous_raw.get("enabled", False)),
        class_ids=_as_int_list(
            dangerous_raw.get("class_ids"), [34, 43, 76]
        ),
        polygon=_as_points(dangerous_raw.get("polygon")),
        confirm_s=float(dangerous_raw.get("confirm_s", 0.5)),
        cooldown_s=float(dangerous_raw.get("cooldown_s", 30.0)),
    )

    vandalism_raw = analytics.get("vandalism", {}) or {}
    vandalism = VandalismConfig(
        enabled=bool(vandalism_raw.get("enabled", False)),
        class_ids=_as_int_list(vandalism_raw.get("class_ids"), []),
        polygon=_as_points(vandalism_raw.get("polygon")),
        confirm_s=float(vandalism_raw.get("confirm_s", 1.5)),
        cooldown_s=float(vandalism_raw.get("cooldown_s", 60.0)),
    )

    fall_raw = analytics.get("fall_on_tracks", {}) or {}
    fall_on_tracks = FallOnTracksConfig(
        enabled=bool(fall_raw.get("enabled", False)),
        polygon=_as_points(fall_raw.get("polygon")),
        person_class_ids=_as_int_list(
            fall_raw.get("person_class_ids"), [0]
        ),
        horizontal_ratio=float(fall_raw.get("horizontal_ratio", 1.15)),
        min_vertical_drop_norm=float(
            fall_raw.get("min_vertical_drop_norm", 0.06)
        ),
        confirm_s=float(fall_raw.get("confirm_s", 1.0)),
        cooldown_s=float(fall_raw.get("cooldown_s", 60.0)),
    )

    health_raw = analytics.get("health", {}) or {}
    health = HealthConfig(
        enabled=bool(health_raw.get("enabled", True)),
        offline_after_s=float(health_raw.get("offline_after_s", 8.0)),
        black_luma_threshold=float(
            health_raw.get("black_luma_threshold", 5.0)
        ),
        black_after_s=float(health_raw.get("black_after_s", 3.0)),
        frozen_mean_delta=float(
            health_raw.get("frozen_mean_delta", 0.35)
        ),
        frozen_after_s=float(health_raw.get("frozen_after_s", 10.0)),
        blur_variance_threshold=float(
            health_raw.get("blur_variance_threshold", 4.0)
        ),
        blur_after_s=float(health_raw.get("blur_after_s", 5.0)),
        low_fps_threshold=float(health_raw.get("low_fps_threshold", 1.0)),
        low_fps_after_s=float(health_raw.get("low_fps_after_s", 10.0)),
        cooldown_s=float(health_raw.get("cooldown_s", 60.0)),
    )

    if "uri" not in src:
        raise ValueError("Missing required configuration field: source.uri")

    source_mode = str(src.get("mode", "stream")).lower()
    if source_mode not in {"stream", "snapshot", "youtube"}:
        raise ValueError("source.mode must be 'stream', 'snapshot' or 'youtube'")
    if source_mode == "youtube" and not isinstance(src["uri"], str):
        raise ValueError("YouTube source.uri must be a URL string")
    youtube_max_height = int(src.get("youtube_max_height", 720))
    if youtube_max_height <= 0:
        raise ValueError("source.youtube_max_height must be greater than zero")

    model_classes = _as_int_list(
        model.get("classes"),
        [0, 6, *range(14, 24), 24, 26, 28, 34, 43, 76],
    )

    quantize = model.get("quantize")
    if quantize in (None, "", False):
        quantize = 16 if bool(model.get("half", False)) else None
    elif isinstance(quantize, bool):
        raise ValueError("model.quantize must be 16, 32 or null")
    elif isinstance(quantize, str):
        normalized = quantize.strip().lower()
        aliases = {"16": 16, "fp16": 16, "32": 32, "fp32": 32}
        if normalized not in aliases:
            raise ValueError("model.quantize must be 16/fp16, 32/fp32 or null")
        quantize = aliases[normalized]
    elif isinstance(quantize, (int, float)) and not isinstance(quantize, bool):
        if int(quantize) != quantize or int(quantize) not in {16, 32}:
            raise ValueError("model.quantize must be 16, 32 or null")
        quantize = int(quantize)
    else:
        raise ValueError("model.quantize must be 16, 32 or null")

    def require_model_classes(name: str, enabled: bool, class_ids: list[int]) -> None:
        if not enabled:
            return
        if not class_ids:
            raise ValueError(f"analytics.{name}.class_ids cannot be empty when enabled")
        missing = sorted(set(class_ids) - set(model_classes))
        if missing:
            raise ValueError(
                f"analytics.{name} requires class IDs missing from model.classes: "
                + ", ".join(str(item) for item in missing)
            )

    require_model_classes("luggage", luggage.enabled, luggage.object_class_ids)
    require_model_classes("train", train.enabled, train.class_ids)
    require_model_classes("animal", animal.enabled, animal.animal_class_ids)
    require_model_classes("litter", litter.enabled, litter.class_ids)
    require_model_classes(
        "dangerous_objects", dangerous_objects.enabled, dangerous_objects.class_ids
    )
    require_model_classes("vandalism", vandalism.enabled, vandalism.class_ids)
    require_model_classes(
        "fall_on_tracks", fall_on_tracks.enabled, fall_on_tracks.person_class_ids
    )
    # An empty train polygon is a valid calibration state. The analytics engine
    # keeps train presence UNKNOWN until a polygon is configured, which is safer
    # than forcing operators to draw a replacement just to remove old geometry.
    if fall_on_tracks.enabled and not fall_on_tracks.polygon:
        raise ValueError(
            "analytics.fall_on_tracks.polygon is required when fall detection is enabled"
        )
    guarded_lines = [line.name for line in line_crossings if line.require_train_absent]
    if guarded_lines and not train.enabled:
        raise ValueError(
            "train presence must be enabled for guarded line crossings: "
            + ", ".join(guarded_lines)
        )

    display_scale = float(output.get("display_scale", 1.0))
    if display_scale <= 0:
        raise ValueError("output.display_scale must be greater than zero")
    status_every_s = float(output.get("status_every_s", 2.0))
    if status_every_s < 0:
        raise ValueError("output.status_every_s cannot be negative")

    team_b_enabled = bool(team_b.get("enabled", False))
    team_b_platform = _nullable_string(team_b.get("platform_id"))
    team_b_location = _nullable_string(team_b.get("specific_location"))
    team_b_device = _nullable_string(team_b.get("source_device_id"))
    people_flow_every_s = float(team_b.get("people_flow_every_s", 5.0))
    if people_flow_every_s < 0:
        raise ValueError("team_b.people_flow_every_s cannot be negative")
    if team_b_enabled:
        missing = [
            name
            for name, value in (
                ("platform_id", team_b_platform),
                ("specific_location", team_b_location),
                ("source_device_id", team_b_device),
            )
            if value is None
        ]
        if missing:
            raise ValueError(
                "Team B output is enabled but these fields are missing: "
                + ", ".join(f"team_b.{name}" for name in missing)
            )
        if team_b_platform not in {
            "PLATFORM_1",
            "PLATFORM_2",
            "PLATFORM_3",
            "PLATFORM_4",
        }:
            raise ValueError("team_b.platform_id is not supported by Team B")
        if team_b_location not in {
            "PLATFORM_1",
            "PLATFORM_2",
            "PLATFORM_3",
            "PLATFORM_4",
            "WAITING_AREA",
        }:
            raise ValueError(
                "team_b.specific_location is not supported by Team B"
            )

    people_flow_jsonl_path = _nullable_string(
        team_b.get(
            "people_flow_jsonl_path",
            "outputs/team_b_people_flow.jsonl",
        )
    )
    events_jsonl_path = _nullable_string(
        team_b.get("events_jsonl_path", "outputs/team_b_events.jsonl")
    )
    event_id_db_path = _nullable_string(
        team_b.get("event_id_db_path", "outputs/team_b_state.sqlite3")
    )
    if team_b_enabled and (
        people_flow_jsonl_path is None
        or events_jsonl_path is None
        or event_id_db_path is None
    ):
        raise ValueError("Team B output paths cannot be empty")

    yellow_line_names = _as_string_list(team_b.get("yellow_line_names"))
    restricted_zone_names = _as_string_list(
        team_b.get("restricted_zone_names")
    )
    if team_b_enabled:
        configured_lines = {item.name: item for item in line_crossings}
        unknown_lines = sorted(set(yellow_line_names) - set(configured_lines))
        if unknown_lines:
            raise ValueError(
                "Team B yellow lines are not configured in analytics.line_crossings: "
                + ", ".join(unknown_lines)
            )
        non_prohibited = sorted(
            name
            for name in yellow_line_names
            if configured_lines[name].prohibited_direction is None
        )
        if non_prohibited:
            raise ValueError(
                "Team B yellow lines require prohibited_direction: "
                + ", ".join(non_prohibited)
            )
        unguarded = sorted(
            name
            for name in yellow_line_names
            if not configured_lines[name].require_train_absent
        )
        if unguarded:
            raise ValueError(
                "Team B yellow lines must require confirmed train absence: "
                + ", ".join(unguarded)
            )
        configured_restricted = {item.name for item in restricted_zones}
        unknown_restricted = sorted(
            set(restricted_zone_names) - configured_restricted
        )
        if unknown_restricted:
            raise ValueError(
                "Team B restricted zones are not configured in "
                "analytics.restricted_zones: "
                + ", ".join(unknown_restricted)
            )

    return AppConfig(
        source=SourceConfig(
            uri=_coerce_source_uri(src["uri"]),
            mode=source_mode,
            target_fps=float(src.get("target_fps", 10.0)),
            snapshot_timeout_s=float(src.get("snapshot_timeout_s", 5.0)),
            reconnect_delay_s=float(src.get("reconnect_delay_s", 3.0)),
            startup_timeout_s=float(src.get("startup_timeout_s", 12.0)),
            open_timeout_ms=int(src.get("open_timeout_ms", 8_000)),
            read_timeout_ms=int(src.get("read_timeout_ms", 8_000)),
            loop_file=bool(src.get("loop_file", False)),
            max_frame_age_s=_nullable_float(src.get("max_frame_age_s", 5.0)),
            youtube_max_height=youtube_max_height,
            youtube_cookies_from_browser=_nullable_string(
                src.get("youtube_cookies_from_browser")
            ),
        ),
        model=ModelConfig(
            weights=str(model.get("weights", "yolo12n.pt")),
            device=str(model.get("device", "auto")),
            confidence=float(model.get("confidence", 0.4)),
            iou=float(model.get("iou", 0.5)),
            image_size=int(model.get("image_size", 640)),
            tracker=str(model.get("tracker", "bytetrack.yaml")),
            classes=model_classes,
            quantize=quantize,
        ),
        analytics=AnalyticsConfig(
            roi=_as_points(analytics.get("roi")),
            zones=zones,
            line_crossings=line_crossings,
            restricted_zones=restricted_zones,
            crowd_zones=crowd_zones,
            luggage=luggage,
            train=train,
            animal=animal,
            litter=litter,
            dangerous_objects=dangerous_objects,
            vandalism=vandalism,
            fall_on_tracks=fall_on_tracks,
            health=health,
            person_class_ids=_as_int_list(
                analytics.get("person_class_ids"), [0]
            ),
            tail_length=int(analytics.get("tail_length", 30)),
            track_ttl_s=float(analytics.get("track_ttl_s", 2.5)),
            reference_point=str(
                analytics.get("reference_point", "bottom_center")
            ),
            scene_area_m2=_nullable_float(analytics.get("scene_area_m2")),
        ),
        output=OutputConfig(
            display=bool(output.get("display", True)),
            window_name=str(
                output.get("window_name", "EAV Smart Station Analytics")
            ),
            display_scale=display_scale,
            video_path=(
                None
                if output.get("video_path") in (None, "")
                else str(output["video_path"])
            ),
            video_fps=_nullable_float(output.get("video_fps")),
            jsonl_path=(
                None
                if output.get("jsonl_path") in (None, "")
                else str(output["jsonl_path"])
            ),
            event_frames_dir=(
                None
                if output.get("event_frames_dir") in (None, "")
                else str(output.get("event_frames_dir", "outputs/event_frames"))
            ),
            draw_tails=bool(output.get("draw_tails", True)),
            show_confidence=bool(output.get("show_confidence", True)),
            status_every_s=status_every_s,
        ),
        team_b=TeamBOutputConfig(
            enabled=team_b_enabled,
            platform_id=team_b_platform,
            specific_location=team_b_location,
            source_device_id=team_b_device,
            people_flow_every_s=people_flow_every_s,
            people_flow_jsonl_path=(
                people_flow_jsonl_path
                or "outputs/team_b_people_flow.jsonl"
            ),
            events_jsonl_path=(
                events_jsonl_path or "outputs/team_b_events.jsonl"
            ),
            event_id_db_path=(
                event_id_db_path or "outputs/team_b_state.sqlite3"
            ),
            yellow_line_names=yellow_line_names,
            restricted_zone_names=restricted_zone_names,
        ),
    )
