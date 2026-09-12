from pathlib import Path

from crowd_monitor.config import load_config


def test_example_config_is_safe_and_uncalibrated():
    project_root = Path(__file__).resolve().parents[1]
    config = load_config(project_root / "configs" / "camera.example.yaml")

    assert config.source.mode == "snapshot"
    assert config.source.target_fps == 10
    assert config.output.display is True
    assert config.analytics.roi == []
    assert config.analytics.zones == []
    assert config.analytics.line_crossings == []
    assert config.analytics.restricted_zones == []
    assert config.analytics.crowd_zones == []
    assert config.model.classes == [
        0, 6, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 26, 28, 34, 43, 76
    ]
    assert config.analytics.train.enabled is False
    assert config.analytics.health.enabled is True
    assert config.team_b.enabled is False
    assert config.team_b.platform_id is None


def test_local_config_parses_when_present():
    project_root = Path(__file__).resolve().parents[1]
    local_path = project_root / "configs" / "camera.local.yaml"
    if not local_path.exists():
        return

    config = load_config(local_path)
    assert config.source.uri
    assert config.analytics.roi
    assert config.analytics.zones
    assert config.analytics.line_crossings


def test_youtube_example_uses_live_adapter():
    project_root = Path(__file__).resolve().parents[1]
    config = load_config(project_root / "configs" / "youtube.example.yaml")
    assert config.source.mode == "youtube"
    assert config.source.youtube_max_height == 720
    assert "youtube.com/watch" in str(config.source.uri)
    assert config.analytics.train.enabled is False


def test_video_fixture_uses_fp16_quantize_setting():
    project_root = Path(__file__).resolve().parents[1]
    config = load_config(project_root / "tests" / "fixtures" / "video.yaml")
    assert config.model.quantize == 16
