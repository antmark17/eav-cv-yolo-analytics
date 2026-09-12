import numpy as np

from crowd_monitor.cv_live import write_live_jpeg


def test_write_live_jpeg(tmp_path):
    frame = np.zeros((32, 48, 3), dtype=np.uint8)
    target = tmp_path / "live.jpg"
    write_live_jpeg(target, frame)
    data = target.read_bytes()
    assert data[:2] == b"\xff\xd8"
    assert data[-2:] == b"\xff\xd9"
