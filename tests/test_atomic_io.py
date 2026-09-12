import pytest
from crowd_monitor import atomic_io


def test_failed_replace_preserves_previous_snapshot_and_removes_temp(tmp_path, monkeypatch):
    target = tmp_path / 'live.json'
    target.write_bytes(b'previous')
    def fail(*args):
        raise PermissionError('locked')
    monkeypatch.setattr(atomic_io.os, 'replace', fail)
    with pytest.raises(PermissionError):
        atomic_io.write_json(target, {'people': 2})
    assert target.read_bytes() == b'previous'
    assert list(tmp_path.iterdir()) == [target]


def test_only_persistent_state_forces_disk_sync(tmp_path, monkeypatch):
    synced = []
    monkeypatch.setattr(atomic_io.os, 'fsync', synced.append)
    atomic_io.write_json(tmp_path / 'live.json', {'people': 1})
    assert synced == []
    atomic_io.write_json(tmp_path / 'status.json', {'status': 'Risolto'}, durable=True)
    assert len(synced) == 1
