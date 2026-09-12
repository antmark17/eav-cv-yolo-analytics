from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import unittest

from crowd_monitor.config import TeamBOutputConfig
from crowd_monitor.team_b import validate_event, validate_people_flow
from crowd_monitor.team_b_exporter import TeamBLocalExporter


def _analysis(*, people: int, timestamp: float, events: tuple = ()):
    return SimpleNamespace(people=people, timestamp=timestamp, events=events)


def _crossing(timestamp: float):
    return SimpleNamespace(
        event_type="line_crossing",
        timestamp=timestamp,
        severity="critical",
        zone="yellow_line_platform_2",
        object_class="person",
        details={"prohibited": True, "train_state": "ABSENT"},
    )


class TeamBLocalExporterTests(unittest.TestCase):
    def _config(self, directory: str) -> TeamBOutputConfig:
        root = Path(directory)
        return TeamBOutputConfig(
            enabled=True,
            platform_id="PLATFORM_2",
            specific_location="PLATFORM_2",
            source_device_id="cam_platform2_04",
            people_flow_every_s=5.0,
            people_flow_jsonl_path=str(root / "people.jsonl"),
            events_jsonl_path=str(root / "events.jsonl"),
            event_id_db_path=str(root / "state.sqlite3"),
            yellow_line_names=["yellow_line_platform_2"],
            restricted_zone_names=["tracks"],
        )

    def test_writes_periodic_people_flow_and_supported_event(self):
        with TemporaryDirectory() as directory:
            config = self._config(directory)
            with TeamBLocalExporter(config) as exporter:
                first = exporter.process(
                    _analysis(
                        people=2,
                        timestamp=1783770842.35,
                        events=(_crossing(1783770845.0),),
                    ),
                    monotonic_timestamp=100.0,
                )
                second = exporter.process(
                    _analysis(people=3, timestamp=1783770843.0),
                    monotonic_timestamp=104.9,
                )
                third = exporter.process(
                    _analysis(people=4, timestamp=1783770844.0),
                    monotonic_timestamp=105.0,
                )

            people_lines = [
                json.loads(line)
                for line in Path(config.people_flow_jsonl_path).read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            event_lines = [
                json.loads(line)
                for line in Path(config.events_jsonl_path).read_text(
                    encoding="utf-8"
                ).splitlines()
            ]

        self.assertEqual(len(first.people_flow), 1)
        self.assertEqual(len(first.events), 1)
        self.assertEqual(second.people_flow, ())
        self.assertEqual(len(third.people_flow), 1)
        self.assertEqual([item["value"] for item in people_lines], [2, 4])
        self.assertEqual(event_lines[0]["event_id"], 1)
        for item in people_lines:
            validate_people_flow(item)
        for item in event_lines:
            validate_event(item)

    def test_unsupported_event_is_skipped_without_consuming_an_id(self):
        unsupported = SimpleNamespace(
            event_type="unattended_luggage",
            timestamp=1783770845.0,
            severity="critical",
            zone=None,
            object_class="suitcase",
            details={},
        )
        with TemporaryDirectory() as directory:
            config = self._config(directory)
            with TeamBLocalExporter(config) as exporter:
                skipped = exporter.process(
                    _analysis(
                        people=1,
                        timestamp=1783770845.0,
                        events=(unsupported,),
                    ),
                    monotonic_timestamp=100.0,
                )
                emitted = exporter.process(
                    _analysis(
                        people=1,
                        timestamp=1783770846.0,
                        events=(_crossing(1783770846.0),),
                    ),
                    monotonic_timestamp=101.0,
                )

        self.assertEqual(skipped.skipped_events, 1)
        self.assertEqual(skipped.events, ())
        self.assertEqual(emitted.events[0]["event_id"], 1)

    def test_event_ids_continue_after_exporter_restart(self):
        with TemporaryDirectory() as directory:
            config = self._config(directory)
            with TeamBLocalExporter(config) as exporter:
                first = exporter.process(
                    _analysis(
                        people=1,
                        timestamp=1783770845.0,
                        events=(_crossing(1783770845.0),),
                    ),
                    monotonic_timestamp=100.0,
                )
            with TeamBLocalExporter(config) as exporter:
                second = exporter.process(
                    _analysis(
                        people=1,
                        timestamp=1783770846.0,
                        events=(_crossing(1783770846.0),),
                    ),
                    monotonic_timestamp=101.0,
                )

        self.assertEqual(first.events[0]["event_id"], 1)
        self.assertEqual(second.events[0]["event_id"], 2)

    def test_output_files_and_state_database_must_be_distinct(self):
        with TemporaryDirectory() as directory:
            config = self._config(directory)
            config.events_jsonl_path = config.event_id_db_path
            with self.assertRaisesRegex(ValueError, "must be different"):
                TeamBLocalExporter(config)

    def test_out_of_band_malfunction_does_not_emit_people_flow(self):
        malfunction = SimpleNamespace(
            event_type="malfunction",
            timestamp=1783770845.0,
            severity="critical",
            zone=None,
            object_class=None,
            details={"kind": "offline"},
        )
        with TemporaryDirectory() as directory:
            config = self._config(directory)
            with TeamBLocalExporter(config) as exporter:
                batch = exporter.process_events((malfunction,))
        self.assertEqual(batch.people_flow, ())
        self.assertEqual(len(batch.events), 1)
        self.assertEqual(batch.events[0]["event"]["type"], "malfunction")


if __name__ == "__main__":
    unittest.main()
