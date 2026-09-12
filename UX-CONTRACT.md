# EAV UI contract

Source: presentation API, DemoConfigService, AccessTokens and EventStatusStore.
Locale it-IT, timestamps Europe/Rome. Audience Italy; no Japan-specific scope.

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Select/Listbox | Native select | This contract | Platform-owned popup accepted for ordering/geometries/directions | Keyboard and narrow viewport |
| Form | OperatorLogin / demo Field | Backend allow-list | token masked; numeric tuning; nullable density | Typecheck and API tests |
| Scrollbar | globals.css | DESIGN.md | document; bounded event/point lists | Browser overflow check |
| Toast | notice and role=status | Server result | operator action; demo save | API and browser |
| CRUD | DemoConfigService and Console AI | YAML / load_config | create and edit geometry, no delete workflow | tests/test_demo_config.py |

Public station requires no credentials. Operator and demo use the same operator secret; sessionStorage key eav_operator_session only (signed session token and server expiry, never the operator credential). Native EventSource/MJPEG retain the existing scoped query-token transport for this local demo; other requests use Authorization headers. Server redacts query tokens. No enterprise authentication or remote deployment is implied.

Event status changes stay on the same queue and details; wait for confirmation and block duplicate mutation. The queue keeps up to 1000 events and offers recent/priority sorting. Technical stream keeps 200. Passenger history is an in-memory rolling 300 samples, no database or fabricated data.

Configuration edits are drafts. Apply geometry first, save the full configurable subset second. Server validates unknown keys, finite normalized coordinates and thresholds before atomic replacement. Failure preserves draft; success reports restart required. In-app exit while dirty requires the shared Modal; actual unload uses beforeunload. Backend allows nullable density thresholds and empty global ROI (disabled); zone and train polygons require at least three points in updates.

Loading, no events, missing video, offline streams and failed writes have text states. Previously received data remains visible while streams reconnect. Modal keyboard focus is contained, Escape closes and focus returns to trigger. Geometry supports numeric coordinate entry as a keyboard alternative to clicking the canvas. Native select popup ownership is intentional and accepted on Windows.


## v0.8.0 — decisioni richieste dall’utente
- `operator-session.ts` owns session persistence and expiry. POST /api/auth/session validates the operator credential and returns a signed, unique token valid for 900 seconds. The deadline is absolute from login, not extended by activity or navigation. Closing the tab ends browser persistence. Existing local scripts retain credential access.
- Leaving operator view returns home without deleting the session. Both Console AI exits return to /?view=operator. Expiry requests login again; Console AI preserves unsaved drafts in memory during reauthentication.
- Event status updates reclassify the event but do not select its destination queue. The open detail updates in place.
- Geometry deletion uses Modal confirmation; Add area and Apply geometry are primary within their steps. Save configuration is the primary persistent action, sticky on desktop and in normal flow on small screens.
- Field owns hints, explicit numeric bounds and accessible validation. Nullable area/density values retain their server meaning. Distances are fractions of the image diagonal, not metres.
