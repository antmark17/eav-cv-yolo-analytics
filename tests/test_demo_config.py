from pathlib import Path
from copy import deepcopy
import math
import pytest
import yaml
from crowd_monitor.demo_config import DemoConfigService, PreviewError

@pytest.fixture
def service(tmp_path):
    path=tmp_path/'video.yaml'
    path.write_text(Path('tests/fixtures/video.yaml').read_text(encoding='utf-8'),encoding='utf-8')
    fixture = yaml.safe_load(path.read_text(encoding='utf-8'))
    fixture['analytics']['line_crossings'][0]['class_ids'] = [0]
    fixture['analytics']['line_crossings'][0]['color'] = [0, 255, 255]
    path.write_text(yaml.safe_dump(fixture), encoding='utf-8')
    return DemoConfigService(path)

def test_get_sanitized_config(service):
    c=service.get_public_config()
    assert set(c)=={'model','analytics','restart_required'}
    assert 'weights' not in c['model']
    assert 'source' not in c
    assert 'object_class_ids' not in c['analytics']['luggage']

def test_update_roi(service):
    roi=[[.1,.1],[.8,.1],[.8,.8]]
    result=service.update_config({'analytics':{'roi':roi}})
    assert result['analytics']['roi']==[(.1,.1),(.8,.1),(.8,.8)]
    assert result['restart_required']
    assert yaml.safe_load(service.path.read_text())['analytics']['roi']==roi

def test_update_line_crossing(service):
    old=yaml.safe_load(service.path.read_text())
    lines=service.get_public_config()['analytics']['line_crossings']
    lines[0]['line']=[[.1,.1],[.9,.9]]
    lines[0]['require_train_absent']=True
    service.update_config({'analytics':{'line_crossings':lines}})
    raw=yaml.safe_load(service.path.read_text())
    assert raw['analytics']['line_crossings'][0]['require_train_absent'] is True
    assert raw['analytics']['line_crossings'][0]['class_ids']==old['analytics']['line_crossings'][0]['class_ids']
    assert raw['source']==old['source']

def test_all_editable_geometry_can_be_removed(service):
    result=service.update_config({'analytics':{
        'roi':[],
        'train':{'polygon':[]},
        'crowd_zones':[],
        'line_crossings':[],
    }})
    assert result['analytics']['roi']==[]
    assert result['analytics']['train']['polygon']==[]
    assert result['analytics']['crowd_zones']==[]
    assert result['analytics']['line_crossings']==[]
    raw=yaml.safe_load(service.path.read_text())
    assert raw['analytics']['train']['enabled'] is True
    assert raw['analytics']['train']['polygon']==[]

@pytest.mark.parametrize('roi',[[[-.1,.2],[.8,.2],[.8,.8]],[[1.1,.2],[.8,.2],[.8,.8]],[[.1,-.2],[.8,.2],[.8,.8]],[[.1,1.2],[.8,.2],[.8,.8]],[[.1,.2],[.8,.2]],[[math.nan,.1],[.5,.5],[.9,.1]],[[True,.1],[.5,.5],[.9,.1]]])
def test_invalid_update_does_not_modify_yaml(service,roi):
    before=service.path.read_bytes()
    with pytest.raises(ValueError):service.update_config({'analytics':{'roi':roi}})
    assert service.path.read_bytes()==before

@pytest.mark.parametrize('line',[[[.1,.1]],[[.1,.1],[.1,.1]],[[.1,.1],[.3,.3],[.9,.9]]])
def test_reject_invalid_line(service,line):
    lines=service.get_public_config()['analytics']['line_crossings'];lines[0]['line']=line
    before=service.path.read_bytes()
    with pytest.raises(ValueError):service.update_config({'analytics':{'line_crossings':lines}})
    assert service.path.read_bytes()==before

@pytest.mark.parametrize('patch',[{'source':{'uri':'secret'}},{'model':{'weights':'other'}},{'analytics':{'train':{'enabled':False}}},{'analytics':{'luggage':{'cooldown_s':-1}}},{'analytics':{'animal':{'require_owner_association':'false'}}},{'model':{'confidence':1.1}},{'model':{'image_size':32.5}},{'model':{'iou':math.inf}}])
def test_reject_unknown_or_invalid_tuning(service,patch):
    before=service.path.read_bytes()
    with pytest.raises(ValueError):service.update_config(patch)
    assert service.path.read_bytes()==before

def test_density_threshold_order(service):
    zones=service.get_public_config()['analytics']['crowd_zones'];zones[0].update(warning_density=2,critical_density=1)
    with pytest.raises(ValueError):service.update_config({'analytics':{'crowd_zones':zones}})

def test_entire_config_validated_before_commit(service,monkeypatch):
    before=service.path.read_bytes()
    monkeypatch.setattr('crowd_monitor.demo_config.load_config',lambda path: (_ for _ in ()).throw(ValueError('bad full config')))
    with pytest.raises(ValueError):service.update_config({'model':{'confidence':.3}})
    assert service.path.read_bytes()==before
    assert list(service.path.parent.glob('*.yaml'))==[service.path]

def test_preview_frame_from_configured_video(service,tmp_path):
    import cv2
    import numpy as np
    video=tmp_path/'preview.avi'
    writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),10,(64,48))
    for i in range(10):writer.write(np.full((48,64,3),i*20,dtype=np.uint8))
    writer.release()
    data=yaml.safe_load(service.path.read_text());data['source']['uri']=str(video);service.path.write_text(yaml.safe_dump(data))
    frame=service.get_preview_frame(time_s=.2)
    assert frame.startswith(b'\xff\xd8')
    assert cv2.imdecode(np.frombuffer(frame,dtype=np.uint8),1).shape[:2]==(48,64)
    with pytest.raises(PreviewError):service.get_preview_frame(time_s=30)
    for t in [-1,math.nan,math.inf]:
        with pytest.raises(PreviewError) as e:service.get_preview_frame(time_s=t)
        assert e.value.status==400

def test_preview_missing_file(service):
    raw=yaml.safe_load(service.path.read_text());raw['source']['uri']='nonexistent.mp4';service.path.write_text(yaml.safe_dump(raw))
    with pytest.raises(PreviewError) as e:service.get_preview_frame()
    assert e.value.status==404


def test_config_without_train_polygon_still_allows_other_tuning(service):
    raw=yaml.safe_load(service.path.read_text())
    raw['analytics']['train']['polygon']=None
    raw['analytics']['train']['enabled']=False
    service.path.write_text(yaml.safe_dump(raw))
    assert service.update_config({'model':{'confidence':.4}})['model']['confidence']==.4

def test_rename_preserves_non_exposed_fields(service):
    raw=yaml.safe_load(service.path.read_text())
    lines=service.get_public_config()['analytics']['line_crossings']
    lines[0]['name']='linea_rinominata'
    service.update_config({'analytics':{'line_crossings':lines}})
    saved=yaml.safe_load(service.path.read_text())
    assert saved['analytics']['line_crossings'][0]['color']==raw['analytics']['line_crossings'][0]['color']
    assert saved['analytics']['line_crossings'][0]['class_ids']==raw['analytics']['line_crossings'][0]['class_ids']

def test_add_crowd_zone_and_train_polygon(service):
    zones=service.get_public_config()['analytics']['crowd_zones']
    zones.append({'name':'atrio','polygon':[[.1,.1],[.9,.1],[.9,.9]],'area_m2':40,'warning_density':.5,'critical_density':1.5,'hold_s':3,'cooldown_s':20})
    result=service.update_config({'analytics':{'crowd_zones':zones,'train':{'polygon':[[.1,.1],[.9,.1],[.9,.9]]}}})
    assert result['analytics']['crowd_zones'][-1]['name']=='atrio'
    assert len(result['analytics']['train']['polygon'])==3
