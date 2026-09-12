from crowd_monitor.access_control import AccessTokens, EventStatusStore
import pytest


def test_access_tokens_roles():
    access = AccessTokens("op-secret")
    assert access.is_operator("op-secret")
    assert not access.is_operator("wrong")
    assert not access.is_operator(None)
    assert not access.is_operator("")


def test_event_status_store_persists(tmp_path):
    store = EventStatusStore(tmp_path / "status.json")
    store.update("evt-1", "Preso in carico")
    items = store.apply([{"id": "evt-1"}, {"id": "evt-2"}])
    assert items[0]["status"] == "Preso in carico"
    assert items[1]["status"] == "Nuovo"


@pytest.mark.parametrize("terminal", ["Risolto", "Falso positivo"])
def test_terminal_event_status_cannot_be_reopened(tmp_path, terminal):
    store = EventStatusStore(tmp_path / "status.json")
    store.update("evt-1", terminal)
    with pytest.raises(ValueError, match="event_status_terminal"):
        store.update("evt-1", "In verifica")
    assert store.apply([{"id": "evt-1"}])[0]["status"] == terminal


def test_session_is_unique_signed_and_expires(monkeypatch):
    monkeypatch.setattr('crowd_monitor.access_control.time.time', lambda: 1000)
    access = AccessTokens('secret')
    session = access.create_session('secret')
    assert session['expires_at'] == 1900
    assert access.create_session('wrong') is None
    assert access.create_session(session['token']) is None
    assert access.create_session('secret')['token'] != session['token']
    assert access.is_operator(session['token'])
    assert not access.is_operator(session['token'].replace('.1900.', '.2900.'))
    assert not AccessTokens('different').is_operator(session['token'])
    monkeypatch.setattr('crowd_monitor.access_control.time.time', lambda: 1900)
    assert not access.is_operator(session['token'])
