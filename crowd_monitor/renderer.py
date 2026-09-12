from __future__ import annotations

import cv2
import numpy as np

from .analytics import AnalysisResult


class CrowdRenderer:
    def __init__(self, draw_tails: bool = True, show_confidence: bool = True) -> None:
        self.draw_tails = draw_tails
        self.show_confidence = show_confidence
        self._event_ttl: dict[str, tuple[int | None, str, int]] = {}

    def clear_transient_state(self) -> None:
        self._event_ttl.clear()

    @staticmethod
    def _panel(
        frame: np.ndarray,
        lines: list[tuple[str, tuple[int, int, int]]],
        origin: tuple[int, int],
        width: int = 260,
    ) -> None:
        x, y = origin
        row_h = 20
        height = 14 + row_h * len(lines)
        cv2.rectangle(frame, (x, y), (x + width, y + height), (0, 0, 0), -1)
        cv2.rectangle(frame, (x, y), (x + width, y + height), (180, 180, 180), 1)
        for i, (text, color) in enumerate(lines):
            cv2.putText(
                frame,
                text,
                (x + 8, y + 20 + i * row_h),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.47,
                color,
                1,
                cv2.LINE_AA,
            )

    @staticmethod
    def _tail_color(index: int, total: int) -> tuple[int, int, int]:
        ratio = 1.0 - index / max(total - 1, 1)
        brightness = max(50, int(255 * ratio))
        return (0, brightness, brightness)

    def render(
        self,
        frame: np.ndarray,
        result: AnalysisResult,
        inference_fps: float,
        processed_fps: float,
        pipeline_latency_ms: float,
    ) -> np.ndarray:
        canvas = frame.copy()

        # Age every event once per rendered frame, independently from whether
        # its track is still visible. This prevents unbounded renderer state.
        for event_id, (track_id, text, frames_left) in list(self._event_ttl.items()):
            frames_left -= 1
            if frames_left <= 0:
                self._event_ttl.pop(event_id, None)
            else:
                self._event_ttl[event_id] = (track_id, text, frames_left)

        if result.roi_px.size:
            cv2.polylines(
                canvas,
                [result.roi_px],
                True,
                (200, 200, 200),
                2,
                cv2.LINE_AA,
            )

        for zone in result.zones:
            if not zone.polygon_px.size:
                continue
            overlay = canvas.copy()
            cv2.fillPoly(overlay, [zone.polygon_px], zone.color)
            alpha = 0.28 if zone.kind == "restricted" else 0.18
            cv2.addWeighted(overlay, alpha, canvas, 1.0 - alpha, 0, canvas)
            cv2.polylines(
                canvas, [zone.polygon_px], True, zone.color, 2, cv2.LINE_AA
            )

        for line in result.lines:
            cv2.line(canvas, line.start, line.end, line.color, 3, cv2.LINE_AA)
            cv2.putText(
                canvas,
                line.name,
                (line.start[0] + 5, max(18, line.start[1] - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                line.color,
                1,
                cv2.LINE_AA,
            )

        for event in result.events:
            label = event.event_type.replace("_", " ")
            if event.direction:
                label += f": {event.direction}"
            self._event_ttl[event.event_id] = (event.track_id, label, 45)

        for track in result.tracks:
            x1, y1, x2, y2 = track.bbox
            is_person = track.class_name == "person" or track.class_id == 0
            box_color = (255, 0, 0) if is_person else (255, 0, 255)
            cv2.rectangle(canvas, (x1, y1), (x2, y2), box_color, 2)
            label = f"{track.class_name} ID {track.track_id}"
            if self.show_confidence:
                label += f" {track.confidence:.2f}"
            cv2.putText(
                canvas,
                label,
                (x1, max(18, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            cv2.circle(canvas, track.point, 4, (0, 0, 255), -1)

            if self.draw_tails and len(track.history) > 1:
                points = list(track.history)
                for i in range(1, len(points)):
                    age = len(points) - 1 - i
                    cv2.line(
                        canvas,
                        points[i - 1],
                        points[i],
                        self._tail_color(age, len(points)),
                        max(1, 4 - age // 8),
                        cv2.LINE_AA,
                    )

            active_labels = [
                text
                for event_track_id, text, _ in self._event_ttl.values()
                if event_track_id == track.track_id
            ]
            for index, text in enumerate(active_labels[:2]):
                cv2.putText(
                    canvas,
                    text,
                    (x1, max(35, y1 - 24 - index * 19)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.52,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )

        tracks_by_id = {track.track_id: track for track in result.tracks}
        for association in result.luggage_associations:
            luggage = tracks_by_id.get(association.luggage_track_id)
            if luggage is None:
                continue
            lx1, ly1, lx2, ly2 = luggage.bbox
            luggage_center = ((lx1 + lx2) // 2, (ly1 + ly2) // 2)
            status_color = {
                "associated": (0, 220, 0),
                "candidate": (0, 220, 220),
                "owner_missing_grace": (0, 165, 255),
                "unattended_pending": (0, 100, 255),
                "alerted": (0, 0, 255),
                "unassociated": (160, 160, 160),
            }.get(association.status, (200, 200, 200))
            owner = (
                None
                if association.owner_track_id is None
                else tracks_by_id.get(association.owner_track_id)
            )
            if owner is not None:
                ox1, oy1, ox2, oy2 = owner.bbox
                owner_center = ((ox1 + ox2) // 2, (oy1 + oy2) // 2)
                cv2.line(
                    canvas,
                    luggage_center,
                    owner_center,
                    status_color,
                    2,
                    cv2.LINE_AA,
                )
            owner_label = (
                "owner ?"
                if association.owner_track_id is None
                else f"owner {association.owner_track_id}"
            )
            cv2.putText(
                canvas,
                f"bag {association.luggage_track_id} -> {owner_label} [{association.status}]",
                (lx1, min(canvas.shape[0] - 8, ly2 + 18)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.46,
                status_color,
                2,
                cv2.LINE_AA,
            )

        global_lines = [
            (f"People: {result.people}", (255, 255, 255)),
            (
                f"Train: {result.train_state}",
                {
                    "PRESENT": (0, 0, 255),
                    "ABSENT": (0, 255, 0),
                    "UNKNOWN": (0, 255, 255),
                }.get(result.train_state, (0, 255, 255)),
            ),
            (f"Processed/display: {processed_fps:.1f} FPS", (0, 255, 0)),
            (f"Inference only: {inference_fps:.1f} FPS", (0, 255, 0)),
            (f"Pipeline latency: {pipeline_latency_ms:.0f} ms", (0, 255, 255)),
        ]
        for class_name, count in sorted(result.objects.items()):
            if class_name != "person":
                global_lines.append((f"{class_name}: {count}", (255, 255, 255)))
        if result.density_people_m2 is not None:
            global_lines.append(
                (f"Density: {result.density_people_m2:.2f} p/m2", (255, 255, 255))
            )
        self._panel(canvas, global_lines, (12, 12), width=275)

        panel_y = 12 + 14 + 20 * len(global_lines) + 8
        for zone in result.zones:
            lines = [
                (f"{zone.name} [{zone.kind}]", zone.color),
                (f"People: {zone.people}", (255, 255, 255)),
            ]
            if zone.level is not None:
                lines.append((f"Level: {zone.level}", (0, 255, 255)))
            if zone.density_people_m2 is not None:
                lines.append(
                    (f"Density: {zone.density_people_m2:.2f} p/m2", (255, 255, 255))
                )
            for label, value in zone.live_directions.items():
                lines.append((f"Live {label}: {value}", (200, 200, 200)))
            if zone.stationary:
                lines.append((f"Stationary: {zone.stationary}", (200, 200, 200)))
            self._panel(canvas, lines, (12, panel_y), width=290)
            panel_y += 14 + 20 * len(lines) + 8

        return canvas
