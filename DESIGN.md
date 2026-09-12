---
version: alpha
name: EAV Smart Station
description: Informazioni di stazione e presidio operativo con gerarchia ispirata alla segnaletica ferroviaria.
colors:
  primary: "#0f5d47"
  background: "#f3f6f4"
  surface: "#ffffff"
  ink: "#14241f"
  danger: "#cc1746"
  muted: "#53655d"
typography:
  display:
    fontFamily: 'Bahnschrift, Arial Narrow, Segoe UI, sans-serif'
  sans:
    fontFamily: 'Segoe UI, system-ui, sans-serif'
  mono:
    fontFamily: 'Consolas, ui-monospace, monospace'
rounded:
  DEFAULT: "12px"
  sm: "8px"
spacing:
  panel: "22px"
  gap: "18px"
components:
  button: {}
  panel: {}
  dialog: {}
---
# EAV Smart Station Design System

## Overview
Product register for EAV station passengers, operators and Console AI users in Italy, in Italian. Passenger use is quick and mobile; operations and calibration favour a desktop. The existing EAV interface and UX-CONTRACT.md govern the scope. Retain its green, red and light surfaces. The signature is railway-sign hierarchy: condensed station headings, fixed numeric metrics and a clear red header rule. Avoid marketing ornament and oversized surveillance panels in the operator view.

Runtime token ownership: frontend/app/globals.css is canonical; this file mirrors its semantic values. --brand maps to primary, --bg to background, --surface to surface, --ink to ink, --red to danger, --muted to secondary text. Existing html[data-theme=dark] overrides these roles. --display-font, --body-font and --data-font own font stacks. No generated adapter or independent theme library.

## Colors
Green carries primary action and normal traffic, red carries EAV identity and event severity. Labels always accompany status colours. Dark theme preserves semantics and lightens text. Charts use --brand over --line; technical geometry uses yellow over the raw frame for visibility.

## Typography
Display headings use locally available Bahnschrift with narrow sans fallbacks; UI body uses Segoe UI; technical coordinates and timestamps use Consolas. No remote font dependency. Data uses tabular numerals. Italian numbers and Rome timestamps are used in public views.

## Layout
Page maximum 1440px; existing operator maximum 1600px. Panels use 22px padding and 18px gaps. Passenger trends and zone panels are paired; operator event queue precedes zone state; Console AI puts live view before calibration. Collapse grids at 1050px and 700px. The document owns page scrolling; only bounded event and coordinate lists scroll internally. Images and charts reserve aspect ratio.

## Elevation & Depth
Use existing soft shadows sparingly. Borders define panel groups. Modal dialog alone has a dim backdrop. Do not elevate every nested field.

## Shapes
12px panels, 8px controls, existing EAV logo block. Chart lines and geometry are utilitarian. Preserve natural platform select popups.

## Components
Shared AppHeader/Kpi, OperatorLogin, Modal and demo Field own repeated behaviour. Buttons have visible focus, hover, disabled and busy states. Modal uses native dialog for focus containment and Escape. Loading and errors use stable readable text. Forms retain values on failure. Success follows confirmed response. Technical configuration has one save action and a restart notice; drawing must be applied or discarded before save. SVG charts include readable accessible summaries and accompanying numeric metrics. Motion is limited to button feedback and disabled under reduced-motion preference.

## Do's and Don'ts
- Keep public data aggregate and operator evidence protected.
- Preserve EAV colours and shared controls across all three views.
- Do not invent passenger history or imply saved configuration is already running.
- Do not let live video dominate the default operator page.


## Console AI v0.8.0
Preserve the EAV identity. Geometry reset is a separated danger outline action; add/apply use existing primary buttons. Save stays visible on desktop without constraining document scrolling, and returns to normal flow on narrow or short viewports. Field help sits below its input. Carousel buttons own a 36px hit target with a separate circular 9px indicator (11px active), avoiding inherited minimum button height stretching the dot. globals.css remains the runtime owner; no palette changes.
