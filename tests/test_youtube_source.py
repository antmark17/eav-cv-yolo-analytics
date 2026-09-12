from crowd_monitor.source import resolve_youtube_stream_url


def test_youtube_resolver_requests_current_bounded_stream():
    captured = {}

    def fake_extractor(url, options):
        captured["url"] = url
        captured["options"] = options
        return "https://media.example/live.m3u8"

    resolved = resolve_youtube_stream_url(
        "https://www.youtube.com/watch?v=Dz-VQup0fCg",
        max_height=720,
        extractor=fake_extractor,
    )
    assert resolved == "https://media.example/live.m3u8"
    assert captured["options"]["format"] == "best[height<=720]/best"
    assert "live_from_start" not in captured["options"]
