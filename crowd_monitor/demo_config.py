"""Allow-listed demo editing; the analysis process remains independent."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from threading import RLock
import math
import os
import tempfile
import yaml
from .config import load_config

MODEL = {'confidence', 'iou', 'image_size'}
CROWD = {'name', 'polygon', 'area_m2', 'warning_density', 'critical_density', 'hold_s', 'cooldown_s'}
LINE = {'name', 'line', 'direction_labels', 'prohibited_direction', 'require_train_absent', 'cooldown_s', 'hysteresis'}
LUGGAGE = {'stationary_s', 'unattended_s', 'association_distance_norm', 'association_confirm_s', 'owner_distance_norm', 'owner_missing_grace_s', 'require_owner_association', 'cooldown_s'}
ANIMAL = {'association_distance_norm', 'association_confirm_s', 'supervision_distance_norm', 'owner_missing_grace_s', 'unsupervised_s', 'require_owner_association', 'cooldown_s'}
SCHEMA = {'model': MODEL, 'analytics': {'roi': None, 'crowd_zones': [CROWD], 'line_crossings': [LINE], 'train': {'polygon'}, 'luggage': LUGGAGE, 'animal': ANIMAL}}

class PreviewError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def subset(data, schema):
    if isinstance(schema, set):
        return {k: deepcopy(data[k]) for k in schema if k in data}
    return {k: ([subset(v, rule[0]) for v in data.get(k, []) or []] if isinstance(rule, list)
                else deepcopy(data.get(k)) if rule is None else subset(data.get(k, {}) or {}, rule))
            for k, rule in schema.items()}


def check_keys(patch, schema, prefix=''):
    if not isinstance(patch, dict):
        raise ValueError(f'{prefix or "config"}: atteso oggetto')
    for key, value in patch.items():
        path = f'{prefix}.{key}' if prefix else key
        if key not in schema:
            raise ValueError(f'{path}: campo non consentito')
        rule = schema[key] if isinstance(schema, dict) else None
        if isinstance(rule, list):
            if not isinstance(value, list) or len(value) > 100:
                raise ValueError(f'{path}: attesa lista (massimo 100 elementi)')
            for item in value: check_keys(item, rule[0], path)
        elif rule is not None: check_keys(value, rule, path)


def geometry(points, line=False, optional=False):
    if optional and points in (None, []): return
    if not isinstance(points, (list, tuple)) or (len(points) != 2 if line else len(points) < 3) or len(points) > 500:
        raise ValueError('Geometria: servono 2 punti per una linea o almeno 3 per un poligono')
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError('Punto non valido')
        for n in point:
            if isinstance(n, bool) or not isinstance(n, (float, int)) or not math.isfinite(n) or not 0 <= n <= 1:
                raise ValueError('Coordinate normalizzate richieste tra 0 e 1')
    if len(set(map(tuple, points))) < (2 if line else 3):
        raise ValueError('I punti della geometria devono essere distinti')


def validate(data):
    def walk(value, key='', parent=''):
        if isinstance(value, dict):
            for k, v in value.items(): walk(v, k, key)
        elif key in {'roi', 'polygon', 'line'}:
            geometry(value, key == 'line', key == 'roi' or parent == 'train')
        elif isinstance(value, (list, tuple)):
            if key == 'direction_labels':
                if len(value) != 2 or any(not isinstance(v, str) or not v.strip() for v in value) or value[0] == value[1]:
                    raise ValueError('Servono due etichette di direzione diverse')
            else:
                for v in value: walk(v)
        elif key in {'require_owner_association', 'require_train_absent'}:
            if type(value) is not bool: raise ValueError(f'{key}: atteso booleano')
        elif key in {'name', 'prohibited_direction'}:
            if key == 'prohibited_direction' and value is None: return
            if not isinstance(value, str) or not value.strip() or len(value) > 100: raise ValueError(f'{key}: nome non valido')
        elif value is None and key in {'area_m2', 'warning_density', 'critical_density'}:
            return
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f'{key}: valore numerico finito non negativo richiesto')
            if key in {'confidence', 'iou'} or key.endswith('_norm') or key == 'hysteresis':
                if value > 1: raise ValueError(f'{key}: massimo 1')
            if key in {'area_m2', 'warning_density', 'critical_density'} and value <= 0:
                raise ValueError(f'{key}: deve essere positivo')
            if key == 'image_size' and (type(value) is not int or not 32 <= value <= 4096):
                raise ValueError('image_size: intero tra 32 e 4096 richiesto')
    walk(data)
    a = data['analytics']
    for collection in ('crowd_zones', 'line_crossings'):
        names = [v['name'] for v in a[collection]]
        if len(names) != len(set(names)): raise ValueError('Nomi duplicati nella stessa raccolta')
    for z in a['crowd_zones']:
        w, c = z.get('warning_density'), z.get('critical_density')
        if w is not None and c is not None and w >= c: raise ValueError('La soglia critica deve superare la soglia di avviso')
    for line in a['line_crossings']:
        if line.get('prohibited_direction') is not None and line['prohibited_direction'] not in line['direction_labels']:
            raise ValueError('La direzione vietata deve corrispondere a una delle etichette')


class DemoConfigService:
    def __init__(self, config_path):
        self.path = Path(config_path).expanduser().resolve()
        self._lock = RLock()
        self.restart_required = False
        # Relative source paths follow the CLI working directory, fixed at startup.
        self.source_base = Path.cwd()

    def get_public_config(self):
        with self._lock:
            data = subset(asdict(load_config(self.path)), SCHEMA)
            data['restart_required'] = self.restart_required
            return data

    def update_config(self, patch):
        check_keys(patch, SCHEMA)
        with self._lock:
            raw = yaml.safe_load(self.path.read_text(encoding='utf-8'))
            candidate = deepcopy(raw)
            def merge(target, change):
                for key, value in change.items():
                    if isinstance(value, dict):
                        if not isinstance(target.get(key), dict): target[key] = {}
                        merge(target[key], value)
                    elif key in {'crowd_zones', 'line_crossings'}:
                        previous = {v['name']: v for v in target.get(key, []) or []}
                        existing = target.get(key, []) or []
                        target[key] = [{**previous.get(v.get('name'), existing[i] if i < len(existing) and len(value) == len(existing) else {}), **deepcopy(v)} for i, v in enumerate(value)]
                    else: target[key] = deepcopy(value)
            merge(candidate, patch)
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', dir=self.path.parent, encoding='utf-8', delete=False) as temp:
                    temp_path = Path(temp.name)
                    yaml.safe_dump(candidate, temp, allow_unicode=True, sort_keys=False)
                    temp.flush()
                    os.fsync(temp.fileno())
                try:
                    config = load_config(temp_path)
                    clean = subset(asdict(config), SCHEMA)
                    # Validate supplied types before load_config can coerce them.
                    validate_patch = deepcopy(clean)
                    merge(validate_patch, patch)
                    validate(validate_patch)
                except (KeyError, TypeError, ValueError, AttributeError) as exc:
                    raise ValueError('Configurazione non valida: ' + str(exc)) from exc
                os.replace(temp_path, self.path)
                self.restart_required = True
            finally:
                if temp_path is not None: temp_path.unlink(missing_ok=True)
            return self.get_public_config()

    def get_preview_frame(self, *, time_s=None):
        if time_s is not None and (not math.isfinite(time_s) or time_s < 0):
            raise PreviewError('Il tempo deve essere finito e non negativo', 400)
        with self._lock:
            source = load_config(self.path).source.uri
        if not isinstance(source, str) or '://' in source:
            raise PreviewError('La preview richiede un file video locale')
        path = Path(source).expanduser()
        if not path.is_absolute(): path = self.source_base / path
        if not path.is_file(): raise PreviewError('Video configurato non trovato', 404)
        import cv2
        cap = cv2.VideoCapture(str(path))
        try:
            if not cap.isOpened(): raise PreviewError('Video configurato non apribile')
            if time_s is not None:
                fps, count = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
                if fps > 0 and count > 0 and time_s >= count / fps:
                    raise PreviewError('Tempo oltre la durata del video')
                cap.set(cv2.CAP_PROP_POS_MSEC, time_s * 1000)
            ok, frame = cap.read()
            if not ok: raise PreviewError('Frame non disponibile al tempo richiesto')
            ok, encoded = cv2.imencode('.jpg', frame)
            if not ok: raise PreviewError('Impossibile creare la preview')
            return encoded.tobytes()
        finally:
            cap.release()
