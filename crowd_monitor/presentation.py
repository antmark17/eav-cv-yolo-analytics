"""Explicit public/operator contracts, independent of HTTP transport."""

def congestion_level(zones: list[dict]) -> str:
    order = {"critical": 3, "high": 3, "warning": 2, "medium": 2, "normal": 1, "low": 1}
    best = (0, "unknown")
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        raw = str(zone.get("level") or "").lower()
        score = order.get(raw, 0)
        if score > best[0]:
            best = (score, "high" if score == 3 else "medium" if score == 2 else "low")
    return best[1]

def public_station_state(state: dict, *, updated_at: float | None = None) -> dict:
    zones_out = []
    for zone in state.get("zones", []) if isinstance(state.get("zones"), list) else []:
        if not isinstance(zone, dict):
            continue
        # Only crowd zones are useful to the passenger/user view.
        if str(zone.get("kind") or "") not in {"crowd", "density", ""}:
            continue
        zones_out.append({
            "name": zone.get("name") or "Area",
            "people": zone.get("people", 0),
            "density_people_m2": zone.get("density_people_m2"),
            "level": zone.get("level"),
        })
    return {
        "schema_version": "eav-user-congestion-0.7.0",
        "station": state.get("station") or "Stazione EAV",
        "people": state.get("people", 0),
        "congestion": congestion_level(zones_out),
        "density_people_m2": state.get("density_people_m2"),
        "zones": zones_out,
        "updated_at": updated_at,
    }

def operator_live_state(state: dict, *, cv_available: bool, updated_at: float | None = None) -> dict:
    # Deliberately strip the local file/source name from the web contract.
    return {
        "schema_version": "eav-operator-live-0.6.2",
        "station": state.get("station") or "Stazione EAV",
        "people": state.get("people", 0),
        "objects": state.get("objects") if isinstance(state.get("objects"), dict) else {},
        "train_state": state.get("train_state", "UNKNOWN"),
        "density_people_m2": state.get("density_people_m2"),
        "zones": state.get("zones") if isinstance(state.get("zones"), list) else [],
        "cv_available": cv_available,
        "cv_live": bool(state.get("running")) and cv_available,
        "running": bool(state.get("running")),
        "updated_at": updated_at,
    }

