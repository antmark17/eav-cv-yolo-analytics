from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import json
import unittest

from crowd_monitor.team_b import (
    SqliteEventIdStore,
    TeamBNormalizer,
    TeamBValidationError,
    UnsupportedTeamBEventError,
    parse_and_validate_json,
    validate_event,
    validate_people_flow,
)


class TeamBValidationTests(unittest.TestCase):
    def test_valid_people_flow(self):
        validate_people_flow(
            {
                "timestamp": "2026-07-11T11:54:02.350Z",
                "station_id": "STAZIONE_MONTESANTO",
                "platform_id": "PLATFORM_1",
                "metric": "people_count",
                "value": 42,
            }
        )

    def test_people_flow_rejects_bool_and_extra_field(self):
        with self.assertRaises(TeamBValidationError) as raised:
            validate_people_flow(
                {
                    "timestamp": "2026-07-11T11:54:02.350Z",
                    "station_id": "STAZIONE_MONTESANTO",
                    "platform_id": "PLATFORM_1",
                    "metric": "people_count",
                    "value": True,
                    "occupancy": 12,
                }
            )
        self.assertIn("$.value", str(raised.exception))
        self.assertIn("$.occupancy is not allowed", str(raised.exception))

    def test_valid_event_without_optional_snapshot(self):
        validate_event(
            {
                "event_id": 1,
                "timestamp": "2026-07-11T11:54:05Z",
                "station_id": "STAZIONE_MONTESANTO",
                "specific_location": "PLATFORM_2",
                "source_device": {"type": "camera", "id": "camera-001"},
                "event": {
                    "type": "malfunction",
                    "severity": "high",
                    "description": "Camera offline",
                },
            }
        )

    def test_event_rejects_unexpected_nested_field_and_bad_url(self):
        with self.assertRaises(TeamBValidationError) as raised:
            validate_event(
                {
                    "event_id": 1,
                    "timestamp": "2026-07-11T11:54:05Z",
                    "station_id": "STAZIONE_MONTESANTO",
                    "specific_location": "PLATFORM_2",
                    "source_device": {
                        "type": "camera",
                        "id": "camera-001",
                        "name": "not allowed",
                    },
                    "event": {
                        "type": "malfunction",
                        "severity": "high",
                        "description": "Camera offline",
                        "related_data": {"image_frame_url": "not-a-url"},
                    },
                }
            )
        self.assertIn("$.source_device.name is not allowed", str(raised.exception))
        self.assertIn("valid HTTP or HTTPS URL", str(raised.exception))

    def test_parser_rejects_duplicate_json_fields(self):
        raw = json.dumps(
            {
                "timestamp": "2026-07-11T11:54:02.350Z",
                "station_id": "STAZIONE_MONTESANTO",
                "platform_id": "PLATFORM_1",
                "metric": "people_count",
            }
        )[:-1] + ', "metric": "people_count", "value": 1}'
        with self.assertRaises(TeamBValidationError) as raised:
            parse_and_validate_json(raw, "people_flow")
        self.assertIn("duplicate JSON field", str(raised.exception))


class TeamBNormalizerTests(unittest.TestCase):
    def _normalizer(self, path: Path) -> tuple[SqliteEventIdStore, TeamBNormalizer]:
        store = SqliteEventIdStore(path)
        normalizer = TeamBNormalizer(
            platform_id="PLATFORM_2",
            specific_location="PLATFORM_2",
            source_device_id="cam_platform2_04",
            event_ids=store,
            yellow_line_names=frozenset({"yellow_line_platform_2"}),
            restricted_zone_names=frozenset({"tracks"}),
        )
        return store, normalizer

    def test_people_count_is_normalized_to_utc(self):
        with SqliteEventIdStore(":memory:") as store:
            normalizer = TeamBNormalizer(
                platform_id="PLATFORM_1",
                specific_location="PLATFORM_1",
                source_device_id="camera-001",
                event_ids=store,
            )
            payload = normalizer.normalize_people_count(42, 1783770842.35)
        self.assertEqual(payload["timestamp"], "2026-07-11T11:54:02.350Z")
        self.assertEqual(payload["value"], 42)

    def test_event_mapping_and_increment_survive_restart(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite3"
            store, normalizer = self._normalizer(path)
            crossing = SimpleNamespace(
                event_type="line_crossing",
                timestamp=1783770845.0,
                severity="critical",
                zone="yellow_line_platform_2",
                object_class="person",
                details={"prohibited": True, "train_state": "ABSENT"},
            )
            first = normalizer.normalize_event(crossing)
            store.close()

            store, normalizer = self._normalizer(path)
            intrusion = SimpleNamespace(
                event_type="restricted_zone_entry",
                timestamp=1783770846.0,
                severity="warning",
                zone="tracks",
                object_class="person",
                details={},
            )
            second = normalizer.normalize_event(intrusion)
            store.close()

        self.assertEqual(first["event_id"], 1)
        self.assertEqual(first["event"]["type"], "yellow_line_crossing")
        self.assertEqual(first["event"]["severity"], "high")
        self.assertNotIn("related_data", first["event"])
        self.assertEqual(second["event_id"], 2)
        self.assertEqual(second["event"]["type"], "restricted_area_intrusion")
        self.assertEqual(second["event"]["severity"], "medium")

    def test_lab_door_is_not_mislabeled_as_yellow_line(self):
        with SqliteEventIdStore(":memory:") as store:
            normalizer = TeamBNormalizer(
                platform_id="PLATFORM_1",
                specific_location="PLATFORM_1",
                source_device_id="lab-camera",
                event_ids=store,
                yellow_line_names=frozenset({"yellow_line_platform_1"}),
            )
            event = SimpleNamespace(
                event_type="line_crossing",
                timestamp=1783770845.0,
                severity="critical",
                zone="lab_door",
                object_class="person",
                details={"prohibited": True},
            )
            with self.assertRaises(UnsupportedTeamBEventError):
                normalizer.normalize_event(event)

    def test_non_prohibited_crossing_is_not_emitted_as_alert(self):
        with SqliteEventIdStore(":memory:") as store:
            normalizer = TeamBNormalizer(
                platform_id="PLATFORM_1",
                specific_location="PLATFORM_1",
                source_device_id="camera-001",
                event_ids=store,
                yellow_line_names=frozenset({"yellow_line_platform_1"}),
            )
            event = SimpleNamespace(
                event_type="line_crossing",
                timestamp=1783770845.0,
                severity="info",
                zone="yellow_line_platform_1",
                object_class="person",
                details={"prohibited": False},
            )
            with self.assertRaises(UnsupportedTeamBEventError):
                normalizer.normalize_event(event)

    def test_yellow_line_requires_confirmed_train_absence(self):
        with SqliteEventIdStore(":memory:") as store:
            normalizer = TeamBNormalizer(
                platform_id="PLATFORM_1",
                specific_location="PLATFORM_1",
                source_device_id="camera-001",
                event_ids=store,
                yellow_line_names=frozenset({"yellow_line_platform_1"}),
            )
            for train_state in ("PRESENT", "UNKNOWN", None):
                event = SimpleNamespace(
                    event_type="line_crossing",
                    timestamp=1783770845.0,
                    severity="critical",
                    zone="yellow_line_platform_1",
                    object_class="person",
                    details={"prohibited": True, "train_state": train_state},
                )
                with self.assertRaises(UnsupportedTeamBEventError):
                    normalizer.normalize_event(event)

    def test_unattended_luggage_waits_for_contract_extension(self):
        with SqliteEventIdStore(":memory:") as store:
            normalizer = TeamBNormalizer(
                platform_id="PLATFORM_1",
                specific_location="PLATFORM_1",
                source_device_id="camera-001",
                event_ids=store,
            )
            event = SimpleNamespace(
                event_type="unattended_luggage",
                timestamp=1783770845.0,
                severity="critical",
                zone="platform",
                object_class="backpack",
                details={},
            )
            with self.assertRaises(UnsupportedTeamBEventError):
                normalizer.normalize_event(event)

    def test_invalid_payload_does_not_consume_event_id(self):
        with SqliteEventIdStore(":memory:") as store:
            normalizer = TeamBNormalizer(
                platform_id="PLATFORM_1",
                specific_location="PLATFORM_1",
                source_device_id="camera-001",
                event_ids=store,
            )
            malformed = SimpleNamespace(
                event_type="malfunction",
                timestamp="not-a-timestamp",
                severity="critical",
                zone=None,
                object_class=None,
                details={},
            )
            with self.assertRaises(ValueError):
                normalizer.normalize_event(malformed)
            valid = SimpleNamespace(
                event_type="malfunction",
                timestamp=1783770845.0,
                severity="critical",
                zone=None,
                object_class=None,
                details={},
            )
            payload = normalizer.normalize_event(valid)
        self.assertEqual(payload["event_id"], 1)


if __name__ == "__main__":
    unittest.main()
