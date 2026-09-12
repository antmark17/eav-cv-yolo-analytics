from crowd_monitor.analytics import CrowdAnalyticsEngine
from crowd_monitor.config import (
    AnimalSupervisionConfig,
    AnalyticsConfig,
    CrowdZoneConfig,
    DangerousObjectConfig,
    FallOnTracksConfig,
    LineCrossingConfig,
    LitterConfig,
    LuggageConfig,
    RestrictedZoneConfig,
    TrainPresenceConfig,
    VandalismConfig,
)
from crowd_monitor.detector import Detection


def detection(
    track_id: int,
    bbox: tuple[int, int, int, int],
    class_id: int = 0,
    class_name: str = "person",
) -> Detection:
    return Detection(
        track_id=track_id,
        class_id=class_id,
        class_name=class_name,
        bbox=bbox,
        confidence=0.9,
    )


def test_finite_line_crossing_emits_prohibited_event():
    config = AnalyticsConfig(
        line_crossings=[
            LineCrossingConfig(
                name="boundary",
                line=((0.5, 0.0), (0.5, 1.0)),
                direction_labels=("right_to_left", "left_to_right"),
                prohibited_direction="left_to_right",
                cooldown_s=0.0,
                hysteresis=0.0,
            )
        ],
        luggage=LuggageConfig(enabled=False),
    )
    engine = CrowdAnalyticsEngine(config)
    engine.process(
        [detection(1, (20, 20, 40, 80))],
        (100, 100, 3),
        timestamp=1000.0,
        monotonic_timestamp=0.0,
    )
    result = engine.process(
        [detection(1, (60, 20, 80, 80))],
        (100, 100, 3),
        timestamp=1001.0,
        monotonic_timestamp=1.0,
    )
    assert len(result.events) == 1
    event = result.events[0]
    assert event.event_type == "line_crossing"
    assert event.direction == "left_to_right"
    assert event.severity == "critical"


def test_restricted_zone_entry_and_crowd_density_event():
    polygon = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.9), (0.2, 0.9)]
    config = AnalyticsConfig(
        restricted_zones=[
            RestrictedZoneConfig(
                name="tracks",
                polygon=polygon,
                entry_grace_s=0.0,
                repeat_interval_s=30.0,
            )
        ],
        crowd_zones=[
            CrowdZoneConfig(
                name="platform",
                polygon=polygon,
                area_m2=1.0,
                warning_density=1.0,
                critical_density=2.0,
                hold_s=0.0,
                cooldown_s=30.0,
            )
        ],
        luggage=LuggageConfig(enabled=False),
    )
    engine = CrowdAnalyticsEngine(config)
    result = engine.process(
        [detection(1, (30, 20, 50, 70))],
        (100, 100, 3),
        timestamp=1000.0,
        monotonic_timestamp=0.0,
    )
    event_types = {event.event_type for event in result.events}
    assert "restricted_zone_entry" in event_types
    assert "crowd_density" in event_types
    crowd = next(zone for zone in result.zones if zone.kind == "crowd")
    assert crowd.density_people_m2 == 1.0
    assert crowd.level == "warning"


def test_unattended_luggage_requires_stationary_and_unattended_windows():
    config = AnalyticsConfig(
        track_ttl_s=10.0,
        tail_length=20,
        luggage=LuggageConfig(
            enabled=True,
            stationary_s=1.0,
            unattended_s=1.0,
            max_motion_norm=0.02,
            require_owner_association=False,
            owner_distance_norm=0.1,
            cooldown_s=30.0,
        ),
    )
    engine = CrowdAnalyticsEngine(config)
    bag = detection(7, (40, 40, 60, 60), class_id=24, class_name="backpack")
    engine.process(
        [bag], (100, 100, 3), timestamp=1000.0, monotonic_timestamp=0.0
    )
    engine.process(
        [bag], (100, 100, 3), timestamp=1001.0, monotonic_timestamp=1.0
    )
    result = engine.process(
        [bag], (100, 100, 3), timestamp=1002.0, monotonic_timestamp=2.0
    )
    assert len(result.events) == 1
    assert result.events[0].event_type == "unattended_luggage"
    assert result.events[0].object_class == "backpack"


def _guarded_line() -> LineCrossingConfig:
    return LineCrossingConfig(
        name="yellow_line",
        line=((0.5, 0.0), (0.5, 1.0)),
        direction_labels=("right_to_left", "towards_tracks"),
        prohibited_direction="towards_tracks",
        require_train_absent=True,
        cooldown_s=0.0,
        hysteresis=0.0,
    )


def _train(confirm_present: float, confirm_absent: float) -> TrainPresenceConfig:
    return TrainPresenceConfig(
        enabled=True,
        class_ids=[6],
        polygon=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
        present_confirm_s=confirm_present,
        absent_confirm_s=confirm_absent,
    )


def test_yellow_line_is_suppressed_when_train_present():
    engine = CrowdAnalyticsEngine(
        AnalyticsConfig(
            line_crossings=[_guarded_line()],
            train=_train(0.0, 0.0),
            luggage=LuggageConfig(enabled=False),
        )
    )
    train = detection(20, (10, 10, 90, 90), class_id=6, class_name="train")
    engine.process(
        [detection(1, (20, 20, 40, 80)), train],
        (100, 100, 3),
        timestamp=1000.0,
        monotonic_timestamp=0.0,
    )
    result = engine.process(
        [detection(1, (60, 20, 80, 80)), train],
        (100, 100, 3),
        timestamp=1001.0,
        monotonic_timestamp=1.0,
    )
    assert result.train_state == "PRESENT"
    assert "line_crossing" not in {event.event_type for event in result.events}
    suppressed = next(
        event
        for event in result.events
        if event.event_type == "yellow_line_crossing_suppressed"
    )
    assert suppressed.details["train_state"] == "PRESENT"


def test_yellow_line_is_emitted_only_after_confirmed_absence():
    engine = CrowdAnalyticsEngine(
        AnalyticsConfig(
            line_crossings=[_guarded_line()],
            train=_train(0.0, 0.0),
            luggage=LuggageConfig(enabled=False),
        )
    )
    engine.process(
        [detection(1, (20, 20, 40, 80))],
        (100, 100, 3),
        timestamp=1000.0,
        monotonic_timestamp=0.0,
    )
    result = engine.process(
        [detection(1, (60, 20, 80, 80))],
        (100, 100, 3),
        timestamp=1001.0,
        monotonic_timestamp=1.0,
    )
    crossing = next(
        event for event in result.events if event.event_type == "line_crossing"
    )
    assert result.train_state == "ABSENT"
    assert crossing.details["train_state"] == "ABSENT"


def test_unknown_train_state_is_fail_safe():
    engine = CrowdAnalyticsEngine(
        AnalyticsConfig(
            line_crossings=[_guarded_line()],
            train=_train(1.0, 10.0),
            luggage=LuggageConfig(enabled=False),
        )
    )
    engine.process(
        [detection(1, (20, 20, 40, 80))],
        (100, 100, 3),
        timestamp=1000.0,
        monotonic_timestamp=0.0,
    )
    result = engine.process(
        [detection(1, (60, 20, 80, 80))],
        (100, 100, 3),
        timestamp=1001.0,
        monotonic_timestamp=1.0,
    )
    assert result.train_state == "UNKNOWN"
    assert any(
        event.event_type == "yellow_line_crossing_suppressed"
        for event in result.events
    )


def test_luggage_owner_identity_is_not_replaced_by_a_stranger():
    engine = CrowdAnalyticsEngine(
        AnalyticsConfig(
            track_ttl_s=10.0,
            luggage=LuggageConfig(
                enabled=True,
                stationary_s=1.0,
                unattended_s=1.0,
                association_distance_norm=0.2,
                association_confirm_s=0.0,
                owner_distance_norm=0.25,
                owner_missing_grace_s=0.0,
                require_owner_association=True,
                cooldown_s=30.0,
            ),
        )
    )
    owner = detection(1, (30, 20, 45, 80))
    stranger = detection(2, (55, 20, 70, 80))
    bag = detection(7, (42, 55, 52, 70), class_id=24, class_name="backpack")
    engine.process([owner, bag], (100, 100, 3), monotonic_timestamp=0.0)
    engine.process([stranger, bag], (100, 100, 3), monotonic_timestamp=1.0)
    result = engine.process(
        [stranger, bag], (100, 100, 3), monotonic_timestamp=2.0
    )
    event = next(
        event for event in result.events if event.event_type == "unattended_luggage"
    )
    assert event.details["owner_track_id"] == 1


def test_stationary_luggage_history_is_independent_from_short_visual_tail():
    engine = CrowdAnalyticsEngine(
        AnalyticsConfig(
            track_ttl_s=10.0,
            tail_length=3,
            luggage=LuggageConfig(
                enabled=True,
                stationary_s=4.0,
                unattended_s=1.0,
                require_owner_association=False,
                owner_distance_norm=0.1,
                cooldown_s=30.0,
            ),
        )
    )
    bag = detection(7, (40, 40, 60, 60), class_id=24, class_name="backpack")
    result = None
    for second in range(6):
        result = engine.process(
            [bag],
            (100, 100, 3),
            timestamp=1000.0 + second,
            monotonic_timestamp=float(second),
        )
    assert result is not None
    assert any(event.event_type == "unattended_luggage" for event in result.events)
    track = next(item for item in result.tracks if item.track_id == 7)
    assert len(track.history) == 3


def test_owner_candidate_must_persist_before_initial_association():
    engine = CrowdAnalyticsEngine(
        AnalyticsConfig(
            track_ttl_s=10.0,
            luggage=LuggageConfig(
                enabled=True,
                association_distance_norm=0.25,
                association_confirm_s=1.0,
                require_owner_association=True,
            ),
        )
    )
    person = detection(1, (30, 20, 45, 80))
    bag = detection(7, (42, 55, 52, 70), class_id=24, class_name="backpack")

    first = engine.process([person, bag], (100, 100, 3), monotonic_timestamp=0.0)
    assert first.luggage_associations[0].owner_track_id is None
    assert first.luggage_associations[0].candidate_track_id == 1
    assert first.luggage_associations[0].status == "candidate"

    second = engine.process([person, bag], (100, 100, 3), monotonic_timestamp=1.0)
    assert second.luggage_associations[0].owner_track_id == 1
    assert second.luggage_associations[0].status == "associated"


def test_short_owner_id_switch_is_reassociated_near_last_position():
    engine = CrowdAnalyticsEngine(
        AnalyticsConfig(
            track_ttl_s=10.0,
            luggage=LuggageConfig(
                enabled=True,
                stationary_s=1.0,
                unattended_s=1.0,
                association_distance_norm=0.25,
                association_confirm_s=0.0,
                owner_distance_norm=0.3,
                owner_missing_grace_s=0.0,
                owner_reassociation_window_s=2.0,
                owner_reassociation_distance_norm=0.08,
                owner_reassociation_confirm_s=0.0,
                require_owner_association=True,
                cooldown_s=30.0,
            ),
        )
    )
    owner_v1 = detection(1, (30, 20, 45, 80))
    owner_v2 = detection(9, (31, 20, 46, 80))
    bag = detection(7, (42, 55, 52, 70), class_id=24, class_name="backpack")

    engine.process([owner_v1, bag], (100, 100, 3), monotonic_timestamp=0.0)
    switched = engine.process([owner_v2, bag], (100, 100, 3), monotonic_timestamp=1.0)
    assert switched.luggage_associations[0].owner_track_id == 9
    assert switched.luggage_associations[0].status == "associated"

    result = engine.process([owner_v2, bag], (100, 100, 3), monotonic_timestamp=2.0)
    assert not any(event.event_type == "unattended_luggage" for event in result.events)


def test_initially_unassociated_luggage_reports_case():
    engine = CrowdAnalyticsEngine(
        AnalyticsConfig(
            track_ttl_s=10.0,
            luggage=LuggageConfig(
                enabled=True,
                stationary_s=1.0,
                unattended_s=1.0,
                require_owner_association=False,
                owner_distance_norm=0.1,
                cooldown_s=30.0,
            ),
        )
    )
    bag = detection(7, (40, 40, 60, 60), class_id=24, class_name="backpack")
    engine.process([bag], (100, 100, 3), monotonic_timestamp=0.0)
    engine.process([bag], (100, 100, 3), monotonic_timestamp=1.0)
    result = engine.process([bag], (100, 100, 3), monotonic_timestamp=2.0)
    event = next(event for event in result.events if event.event_type == "unattended_luggage")
    assert event.details["case"] == "initially_unassociated"
    assert event.details["episode_id"]


def test_unsupervised_animal_uses_owner_association_and_timer():
    engine = CrowdAnalyticsEngine(
        AnalyticsConfig(
            luggage=LuggageConfig(enabled=False),
            animal=AnimalSupervisionConfig(
                enabled=True,
                animal_class_ids=[16],
                association_distance_norm=0.2,
                supervision_distance_norm=0.25,
                owner_missing_grace_s=0.0,
                unsupervised_s=1.0,
                cooldown_s=30.0,
            ),
        )
    )
    owner = detection(1, (30, 20, 45, 80))
    dog = detection(9, (42, 55, 58, 75), class_id=16, class_name="dog")
    # The supervisor must persist long enough to become associated.
    engine.process([owner, dog], (100, 100, 3), monotonic_timestamp=0.0)
    engine.process([owner, dog], (100, 100, 3), monotonic_timestamp=0.7)
    engine.process([dog], (100, 100, 3), monotonic_timestamp=1.0)
    result = engine.process([dog], (100, 100, 3), monotonic_timestamp=2.0)
    assert any(event.event_type == "unsupervised_animal" for event in result.events)


def test_custom_and_coco_alert_baselines_are_temporally_confirmed():
    config = AnalyticsConfig(
        track_ttl_s=10.0,
        luggage=LuggageConfig(enabled=False),
        litter=LitterConfig(
            enabled=True,
            class_ids=[90],
            stationary_s=1.0,
            persist_s=1.0,
            cooldown_s=30.0,
        ),
        dangerous_objects=DangerousObjectConfig(
            enabled=True, class_ids=[43], confirm_s=1.0, cooldown_s=30.0
        ),
        vandalism=VandalismConfig(
            enabled=True, class_ids=[91], confirm_s=1.0, cooldown_s=30.0
        ),
    )
    engine = CrowdAnalyticsEngine(config)
    litter = detection(30, (10, 10, 20, 20), class_id=90, class_name="litter")
    knife = detection(31, (30, 10, 40, 30), class_id=43, class_name="knife")
    vandal = detection(32, (50, 10, 80, 80), class_id=91, class_name="vandalism")
    engine.process([litter, knife, vandal], (100, 100, 3), monotonic_timestamp=0.0)
    confirmed = engine.process(
        [litter, knife, vandal], (100, 100, 3), monotonic_timestamp=1.0
    )
    confirmed_types = {event.event_type for event in confirmed.events}
    assert "dangerous_object_detected" in confirmed_types
    assert "vandalism_detected" in confirmed_types
    result = engine.process(
        [litter, knife, vandal], (100, 100, 3), monotonic_timestamp=2.0
    )
    types = {event.event_type for event in result.events}
    assert "dirt_detected" in types
    # Knife/vandalism emitted on the previous frame and remain de-duplicated.
    assert "dangerous_object_detected" not in types
    assert "vandalism_detected" not in types


def test_fall_on_tracks_requires_drop_horizontal_posture_and_hold():
    polygon = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    engine = CrowdAnalyticsEngine(
        AnalyticsConfig(
            track_ttl_s=10.0,
            luggage=LuggageConfig(enabled=False),
            fall_on_tracks=FallOnTracksConfig(
                enabled=True,
                polygon=polygon,
                horizontal_ratio=1.1,
                min_vertical_drop_norm=0.1,
                confirm_s=1.0,
                cooldown_s=30.0,
            ),
        )
    )
    standing = detection(1, (40, 10, 55, 60))
    fallen = detection(1, (20, 70, 80, 90))
    engine.process([standing], (100, 100, 3), monotonic_timestamp=0.0)
    engine.process([fallen], (100, 100, 3), monotonic_timestamp=1.0)
    result = engine.process([fallen], (100, 100, 3), monotonic_timestamp=2.0)
    assert any(event.event_type == "fall_on_tracks" for event in result.events)


def test_animal_owner_is_not_replaced_by_nearby_stranger():
    engine = CrowdAnalyticsEngine(
        AnalyticsConfig(
            luggage=LuggageConfig(enabled=False),
            animal=AnimalSupervisionConfig(
                enabled=True,
                animal_class_ids=[16],
                association_distance_norm=0.25,
                association_confirm_s=0.5,
                supervision_distance_norm=0.18,
                owner_missing_grace_s=0.0,
                unsupervised_s=0.5,
                cooldown_s=30.0,
            ),
        )
    )
    owner = detection(1, (35, 20, 50, 80))
    dog = detection(9, (48, 55, 62, 75), class_id=16, class_name="dog")
    engine.process([owner, dog], (100, 100, 3), monotonic_timestamp=0.0)
    engine.process([owner, dog], (100, 100, 3), monotonic_timestamp=0.6)

    # Original owner moves far away while a stranger stays next to the dog.
    owner_far = detection(1, (0, 10, 10, 60))
    stranger = detection(2, (50, 20, 65, 80))
    engine.process([owner_far, stranger, dog], (100, 100, 3), monotonic_timestamp=1.0)
    result = engine.process(
        [owner_far, stranger, dog], (100, 100, 3), monotonic_timestamp=1.6
    )
    event = next(event for event in result.events if event.event_type == "unsupervised_animal")
    assert event.details["owner_track_id"] == 1


def test_animal_owner_short_id_switch_is_reassociated_near_last_position():
    engine = CrowdAnalyticsEngine(
        AnalyticsConfig(
            luggage=LuggageConfig(enabled=False),
            animal=AnimalSupervisionConfig(
                enabled=True,
                animal_class_ids=[16],
                association_distance_norm=0.25,
                association_confirm_s=0.2,
                supervision_distance_norm=0.25,
                owner_missing_grace_s=0.0,
                owner_reassociation_window_s=2.0,
                owner_reassociation_distance_norm=0.15,
                owner_reassociation_confirm_s=0.2,
                unsupervised_s=0.5,
                cooldown_s=30.0,
            ),
        )
    )
    owner = detection(1, (35, 20, 50, 80))
    dog = detection(9, (48, 55, 62, 75), class_id=16, class_name="dog")
    engine.process([owner, dog], (100, 100, 3), monotonic_timestamp=0.0)
    engine.process([owner, dog], (100, 100, 3), monotonic_timestamp=0.3)

    owner_new_id = detection(7, (36, 20, 51, 80))
    engine.process([owner_new_id, dog], (100, 100, 3), monotonic_timestamp=0.4)
    result = engine.process([owner_new_id, dog], (100, 100, 3), monotonic_timestamp=0.7)
    assert not any(event.event_type == "unsupervised_animal" for event in result.events)
    state = engine._animal_states[9]
    assert state.owner_track_id == 7
    assert state.owner_switches == 1
