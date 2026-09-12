from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from io import BytesIO
from threading import Thread
import json

import pytest

from crowd_monitor.access_control import AccessTokens, EventStatusStore
from crowd_monitor.dashboard import CanonicalJsonlDashboardStore
from crowd_monitor.live_state import write_live_state
from crowd_monitor.presentation import public_station_state
from video_event_server import EavApiHandler
from crowd_monitor.demo_config import DemoConfigService
from pathlib import Path


@pytest.fixture
def api(tmp_path):
    state = tmp_path / 'live.json'
    write_live_state(state, {
        'station': 'Test', 'people': 42, 'source': 'private.mp4',
        'train_state': 'ABSENT', 'zones': [
            {'name': 'Banchina', 'kind': 'crowd', 'level': 'normal', 'density_people_m2': 0.2},
            {'name': 'Binari', 'kind': 'restricted', 'level': 'critical'},
        ],
    })
    config_path=tmp_path/'config.yaml'
    config_path.write_text(Path('tests/fixtures/video.yaml').read_text(encoding='utf-8'),encoding='utf-8')
    handler = type('TestHandler', (EavApiHandler,), {
        'access': AccessTokens('op-secret'),
        'demo_config': DemoConfigService(config_path),
        'status_store': EventStatusStore(tmp_path / 'statuses.json'),
        'store': CanonicalJsonlDashboardStore(tmp_path / 'events.jsonl'),
        'live_state_path': state, 'live_cv_path': tmp_path / 'live.jpg',
    })
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    thread.start()
    yield server.server_address
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def request(api, path, *, token=None, body=None, headers=None):
    connection = HTTPConnection(*api, timeout=3)
    headers = dict(headers or {})
    if token:
        headers['Authorization'] = f'Bearer {token}'
    try:
        connection.request('POST' if body is not None else 'GET', path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_roles_and_sanitized_congestion(api):
    assert request(api, '/api/operator/events')[0] == 403
    assert request(api, '/api/operator/events', token='user-secret')[0] == 403
    assert request(api, '/api/operator/events', token='op-secret')[0] == 200
    status, state = request(api, '/api/user/station')
    assert status == 200
    assert state['people'] == 42
    assert state['congestion'] == 'low'
    assert len(state['zones']) == 1
    assert not {'source', 'train_state', 'objects'} & state.keys()
    assert request(api, '/api/user/station')[1] == state


@pytest.mark.parametrize('body', ['{"status": []}', '{"status": {}}', '{"status": null}', '[]', 'invalid'])
def test_invalid_status_returns_400_instead_of_disconnect(api, body):
    assert request(api, '/api/operator/events/evt/status', token='op-secret', body=body)[0] == 400


@pytest.mark.parametrize('status_name', ['Preso in carico', 'In verifica', 'Risolto', 'Falso positivo'])
def test_operator_can_update_event_status(api, status_name):
    body=json.dumps({'status':status_name})
    status,payload=request(api, '/api/operator/events/evt/status', token='op-secret', body=body, headers={'Content-Type':'application/json'})
    assert status==200
    assert payload['ok'] is True
    assert payload['status']==status_name


@pytest.mark.parametrize('terminal', ['Risolto', 'Falso positivo'])
def test_terminal_event_cannot_return_to_active_status(api, terminal):
    headers={'Content-Type':'application/json'}
    first=request(api, '/api/operator/events/evt/status', token='op-secret', body=json.dumps({'status':terminal}), headers=headers)
    assert first[0] == 200
    status,payload=request(api, '/api/operator/events/evt/status', token='op-secret', body=json.dumps({'status':'In verifica'}), headers=headers)
    assert status == 409
    assert payload['error'] == 'event_status_terminal'


@pytest.mark.parametrize('length', ['-1', '5000'])
def test_invalid_body_length_does_not_wait_for_body(api, length):
    assert request(api, '/api/operator/events/evt/status', token='op-secret', body='', headers={'Content-Length': length})[0] == 400


def test_sse_only_publishes_changed_data(monkeypatch):
    handler = object.__new__(EavApiHandler)
    handler.path = "/api/operator/events/stream"
    handler.headers = {"Authorization": "Bearer op-secret"}
    handler.access = AccessTokens("op-secret")
    handler.wfile = BytesIO()
    handler._start_sse = lambda: None
    values = iter([
        {'people': 1, 'updated_at': 1},
        {'people': 1, 'updated_at': 2},
        {'people': 2, 'updated_at': 3},
    ])
    def snapshot():
        try:
            return next(values)
        except StopIteration:
            raise BrokenPipeError
    monkeypatch.setattr('video_event_server.time.sleep', lambda _: None)
    handler._stream_json('operator_live', snapshot)
    output = handler.wfile.getvalue()
    assert output.count(b'event: operator_live') == 2
    assert b'"updated_at": 3' in output


def test_missing_density_has_no_invented_level():
    assert public_station_state({})['congestion'] == 'unknown'


def test_event_stream_starts_with_complete_snapshot(monkeypatch):
    handler = object.__new__(EavApiHandler)
    handler.path = "/api/operator/events/stream"
    handler.headers = {"Authorization": "Bearer op-secret"}
    handler.access = AccessTokens("op-secret")
    handler.wfile = BytesIO()
    handler._start_sse = lambda: None
    handler._operator_events = lambda **kwargs: [{'id': 'event-at-connect', 'status': 'Nuovo'}]
    def disconnect(_):
        raise BrokenPipeError
    monkeypatch.setattr('video_event_server.time.sleep', disconnect)
    handler._stream_events(None)
    output = handler.wfile.getvalue()
    assert b'event: events_snapshot' in output
    assert b'event-at-connect' in output

def test_user_station_stream_is_public(api):
    connection = HTTPConnection(*api, timeout=3)
    try:
        connection.request('GET', '/api/user/station/stream')
        response=connection.getresponse()
        assert response.status==200
        assert response.readline().startswith(b'event: station_congestion')
        data=json.loads(response.readline().decode().removeprefix('data: '))
        assert data['people']==42
        assert 'source' not in data
    finally: connection.close()

@pytest.mark.parametrize('path',['/api/operator/live','/api/operator/live/stream','/api/operator/events/stream','/api/operator/cv/stream','/api/operator/event-frame/test','/api/demo/config','/api/demo/preview-frame'])
def test_protected_endpoints_require_operator_token(api,path):
    assert request(api,path)[0]==403
    assert request(api,path,token='wrong')[0]==403

def test_auth_check_operator_only(api):
    assert request(api,'/api/auth/check')[0]==403
    assert request(api,'/api/auth/check',token='op-secret')[1]=={'ok':True,'role':'operator'}


def test_demo_config_read_write_and_rejection(api):
    assert request(api,'/api/demo/config',token='op-secret')[0]==200
    conn=HTTPConnection(*api,timeout=3)
    try:
        def put(body,token='op-secret'):
            conn.request('PUT','/api/demo/config',json.dumps(body),{'Authorization':f'Bearer {token}','Content-Type':'application/json'})
            response=conn.getresponse()
            return response.status,json.loads(response.read())
        assert put({'model':{'confidence':.31}})[0]==200
        assert put({'model':{'confidence':-1}})[0]==400
        assert request(api,'/api/demo/config',token='op-secret')[1]['model']['confidence']==.31
        assert put({'source':{'uri':'../../secret'}})[0]==400
        assert put({'model':{'confidence':.4}},'wrong')[0]==403
    finally:conn.close()

def test_preview_rejects_browser_paths(api):
    assert request(api,'/api/demo/preview-frame?path=../../secret',token='op-secret')[0]==400
    assert request(api,'/api/demo/preview-frame?time_s=-1',token='op-secret')[0]==400

def test_mjpeg_stream_delivers_protected_jpeg(api,tmp_path):
    import cv2
    import numpy as np
    ok,encoded=cv2.imencode('.jpg',np.zeros((32,48,3),dtype=np.uint8))
    assert ok
    jpeg=encoded.tobytes()
    (tmp_path/'live.jpg').write_bytes(jpeg)
    connection=HTTPConnection(*api,timeout=3)
    try:
        connection.request('GET','/api/operator/cv/stream',headers={'Authorization':'Bearer op-secret'})
        response=connection.getresponse()
        assert response.status==200
        assert response.getheader('Content-Type').startswith('multipart/x-mixed-replace')
        assert response.readline()==b'--eavframe\r\n'
        assert response.readline()==b'Content-Type: image/jpeg\r\n'
        length=int(response.readline().decode().split(':')[1])
        assert response.readline()==b'\r\n'
        assert response.read(length)==jpeg
    finally:connection.close()

def test_event_frame_is_authorized_and_not_public(api,tmp_path):
    import cv2
    import numpy as np
    _,encoded=cv2.imencode('.jpg',np.zeros((32,48,3),dtype=np.uint8))
    frame=tmp_path/'event.jpg';frame.write_bytes(encoded.tobytes())
    event={'timestamp':1,'events':[{'event_id':'protected-frame','event_type':'unattended_luggage','timestamp':1,'severity':'warning','details':{'frame_path':str(frame)}}]}
    (tmp_path/'events.jsonl').write_text(json.dumps(event)+'\n')
    assert request(api,'/api/operator/event-frame/protected-frame')[0]==403
    connection=HTTPConnection(*api,timeout=3)
    try:
        connection.request('GET','/api/operator/event-frame/protected-frame',headers={'Authorization':'Bearer op-secret'})
        response=connection.getresponse()
        assert response.status==200
        assert response.read()==encoded.tobytes()
    finally:connection.close()
    public=request(api,'/api/user/station')[1]
    assert not {'events','frame_url','frame_path','track_id','bbox','confidence','source','frame_index','status'} & public.keys()


def test_event_frame_gallery_exposes_annotated_and_clean_variants(api,tmp_path):
    import cv2
    import numpy as np
    _,annotated=cv2.imencode('.jpg',np.zeros((32,48,3),dtype=np.uint8))
    _,clean=cv2.imencode('.jpg',np.full((32,48,3),180,dtype=np.uint8))
    annotated_path=tmp_path/'annotated.jpg';annotated_path.write_bytes(annotated.tobytes())
    clean_path=tmp_path/'clean.jpg';clean_path.write_bytes(clean.tobytes())
    event={'timestamp':1,'events':[{'event_id':'gallery-frame','event_type':'unattended_luggage','timestamp':1,'severity':'warning','details':{'frame_path':str(annotated_path),'clean_frame_path':str(clean_path)}}]}
    (tmp_path/'events.jsonl').write_text(json.dumps(event)+'\n')

    status,payload=request(api,'/api/operator/events',token='op-secret')
    assert status == 200
    exposed=payload['events'][0]
    assert exposed['frame_url'].endswith('/gallery-frame')
    assert exposed['clean_frame_url'].endswith('/gallery-frame?variant=clean')

    connection=HTTPConnection(*api,timeout=3)
    try:
        connection.request('GET','/api/operator/event-frame/gallery-frame?variant=clean',headers={'Authorization':'Bearer op-secret'})
        response=connection.getresponse()
        assert response.status==200
        assert response.read()==clean.tobytes()
    finally:connection.close()


def test_session_login_and_expiry(api, monkeypatch):
    status, session = request(api, '/api/auth/session', token='op-secret', body='')
    assert status == 200
    assert session['token'] != 'op-secret'
    assert request(api, '/api/auth/check', token=session['token'])[0] == 200
    assert request(api, '/api/auth/session', token=session['token'], body='')[0] == 403
    assert request(api, '/api/auth/session', token='wrong', body='')[0] == 403
    monkeypatch.setattr('crowd_monitor.access_control.time.time', lambda: session['expires_at'])
    assert request(api, '/api/operator/events', token=session['token'])[0] == 403


def test_private_stream_stops_at_session_expiry(monkeypatch):
    access = AccessTokens('op-secret')
    session = access.create_session('op-secret')
    handler = object.__new__(EavApiHandler)
    handler.access = access
    handler.path = '/api/operator/events/stream'
    handler.headers = {'Authorization': 'Bearer ' + session['token']}
    assert handler._stream_authorized()
    monkeypatch.setattr('crowd_monitor.access_control.time.time', lambda: session['expires_at'])
    assert not handler._stream_authorized()
    assert handler.close_connection
