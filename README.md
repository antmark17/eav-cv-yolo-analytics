# EAV CV YOLO Analytics

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/PyTorch-2.14-EE4C2C?logo=pytorch&logoColor=white" alt="PyTorch">
  <img src="https://img.shields.io/badge/Ultralytics-YOLO-111F68?logo=yolo&logoColor=white" alt="Ultralytics YOLO">
  <img src="https://img.shields.io/badge/OpenCV-4.8%2B-5C3EE8?logo=opencv&logoColor=white" alt="OpenCV">
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React">
  <img src="https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white" alt="Next.js">
  <img src="https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/Node.js-22%2B-5FA04E?logo=nodedotjs&logoColor=white" alt="Node.js">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Computer%20Vision-YOLO-blue" alt="Computer Vision">
  <img src="https://img.shields.io/badge/GPU-CUDA-76B900?logo=nvidia&logoColor=white" alt="CUDA">
  <img src="https://img.shields.io/badge/Inference-FP16-orange" alt="FP16">
  <img src="https://img.shields.io/badge/Video-Real--Time-red" alt="Real-Time Video">
  <img src="https://img.shields.io/badge/Tracking-ByteTrack-purple" alt="ByteTrack">
  <img src="https://img.shields.io/badge/Project-EAV%20%C3%97%20Cisco%20DTLab-success" alt="EAV Cisco DTLab">
</p>

A computer vision application for analyzing railway-station video and managing alerts related to crowding, line crossing, unattended baggage, and unattended animals.

The project includes a Python pipeline based on YOLO and ByteTrack, a local API, and a frontend with passenger, operator, and AI Console views for calibration and monitoring.

This project was developed as an **EAV Project Work during the Cisco Digital Transformation Lab (DTLab)**. The repository contains a local demonstrator and its technical material. Without additional hardening, it should not be considered a production-ready video-surveillance system.

## Requirements

- Python 3.10 or newer.
- Node.js 22.13 or newer and npm.
- A video source, either a local file or a supported live source.
- Ultralytics-compatible model weights, for example `yolo12n.pt`.
- To use `cuda:0`: an NVIDIA GPU, up-to-date drivers, and a CUDA-enabled PyTorch build.

The Python dependencies explicitly pin **PyTorch 2.14.0** and **Torchvision 0.29.0**. Inference precision follows the current Ultralytics syntax: `model.quantize: 16` enables **FP16** on compatible hardware, while `model.quantize: null` keeps FP32. In this project, `quantize: 16` refers to FP16 inference precision, not INT16 quantization.

Local video files and model weights are excluded from Git. After cloning the repository, provide the required video and model files separately and configure their paths.

## Windows Installation

Open PowerShell in the project root:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

### Recommended NVIDIA GPU Installation

Install the CUDA-enabled PyTorch build first. The following example uses CUDA 13.0:

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cu130
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
npm --prefix frontend ci
```

PyTorch 2.14.0 is also available with other CUDA builds. Choose the build that matches your installed NVIDIA driver. The version specified in `pyproject.toml` pins the PyTorch release, while the CUDA variant is selected through the package index used by `pip`.

Quick GPU check:

```powershell
.\.venv\Scripts\python.exe -c "import torch; print('torch', torch.__version__); print('cuda runtime', torch.version.cuda); print('cuda available', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

If `cuda available` is `False`, do not use `model.device: cuda:0`. Fix the NVIDIA driver/PyTorch installation, or set `model.device` to `auto` or `cpu`.

### CPU Installation

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
npm --prefix frontend ci
```

If `configs/video.local.yaml` does not exist, create it from the example:

```powershell
Copy-Item configs/video.example.yaml configs/video.local.yaml
```

Configure the following fields in the local YAML file:

- `source.uri`: path or URL of the video source.
- `model.weights`: path to the model weights.
- `model.device`: `cuda:0` for the first NVIDIA GPU, `auto` for automatic selection, or `cpu`.
- `model.quantize`: `16` for FP16 or `null` for FP32.
- Geometry and thresholds under `analytics`: calibrate them for the specific camera view.

The local development copy uses `videos/prova4.mp4`; the generic example uses `videos/clip.mp4` as a placeholder path. Do not overwrite an already calibrated local configuration.

## Running the Application

Open three terminals in the project root.

### 1. API

Set a personal operator token and start the service:

```powershell
$env:EAV_OPERATOR_TOKEN = "YOUR-PERSONAL-OPERATOR-TOKEN"
.\.venv\Scripts\python.exe video_event_server.py --config configs/video.local.yaml
```

The service listens on `http://127.0.0.1:8765`. If no token is provided, the demo fallback is `operator-demo`.

### 2. Frontend

```powershell
npm --prefix frontend run dev
```

Open the address shown in the terminal.

To change the API address, copy `frontend/.env.local.example` to `frontend/.env.local`, update `NEXT_PUBLIC_EAV_EVENT_API`, and restart the frontend.

### 3. Video Analysis

```powershell
.\.venv\Scripts\python.exe run_video.py --video videos/prova4.mp4 --config configs/video.local.yaml --station "EAV Station" --realtime-pacing
```

Change the video path if needed. It should match `source.uri`, which is also used by the AI Console for preview purposes.

The frontend does not automatically start the analysis process.

## Usage

- **Passenger view:** public access to aggregated crowding information.
- **Operator view:** event management and associated image inspection. The operator token is requested on first access and again after 15 minutes from login. Leaving the view does not immediately invalidate the session.
- **AI Console:** calibration of areas, lines, and detection parameters. Exiting the AI Console returns to the operator view.

When an event is acknowledged or resolved, it changes category without forcing the operator away from the currently selected section.

To configure an area, select its type, add points directly on the image or through coordinates, click **Apply geometry**, then **Save configuration**. Geometry deletion requires confirmation. Saved changes are applied after restarting the analysis process.

## Project Structure

| Path | Description |
|---|---|
| `crowd_monitor/` | Acquisition, analysis, configuration, and event-management modules |
| `frontend/` | Web interface and development/build configuration |
| `configs/` | YAML templates and local configurations |
| `tests/` | Python tests, fixtures, and browser validation |
| `docs/` | Architecture and validation documentation |
| `outputs/` | Runtime-generated files, excluded from Git |

Area/line calibration and preview are available in the AI Console.

`run_realtime.py` is the entry point for live sources, while `validate_team_b_json.py` validates exported files.

## Supported Video Sources

The same detection, tracking, and analytics pipeline can run both offline and in real time. The local video used for demonstrations is therefore only one possible input source, not an architectural limitation.

- `stream`: local video files, webcams/camera indices, and OpenCV/FFmpeg-compatible streams, including RTSP, RTMP, and HTTP/HTTPS URLs.
- `snapshot`: an HTTP endpoint returning JPEG images; the application repeatedly acquires snapshots at the configured rate.
- `youtube`: YouTube URLs, including live streams; `yt-dlp` resolves the actual media stream and the application can reopen the source when needed.

For live sources, use `run_realtime.py` with one of the example files in `configs/`.

The live pipeline keeps the most recent frame instead of building an ever-growing queue when inference is slower than the source.

## Validation and Build

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

After building the frontend:

```powershell
npm --prefix frontend start
```

The API and video-analysis processes remain separate.

The Python test suite uses versioned fixtures and does not require `configs/video.local.yaml`.

Additional instructions are available in [docs/VALIDATION.md](docs/VALIDATION.md). Architecture documentation is available in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

The browser test in `tests/browser_v080.mjs` requires Playwright and Chromium. See `docs/VALIDATION.md`. It is not executed automatically by `pytest`.

## Security Notice

The API is designed for local use and listens on `127.0.0.1` by default.

The `operator-demo` token is a demonstration fallback. Before a shared demonstration or any network exposure, always set `EAV_OPERATOR_TOKEN` to a personal value.

Do not expose the server on `0.0.0.0` without additional network protection and authentication.

The project does not implement enterprise-grade authentication or Internet-facing hardening.

## GitHub Repository Notes

The `.gitignore` excludes environments, dependencies, build outputs (`dist`, `.next`, `.vinext`), caches, generated output, videos, model weights, credentials, `.dev.vars`, and local configuration files.

Example files, test fixtures, and `frontend/package-lock.json` should remain versioned.

Before pushing changes, review staged files with:

```powershell
git status
git diff --cached
```

Ignore rules do not remove files that are already tracked. If necessary, remove a file from the Git index without deleting the local copy:

```powershell
git rm --cached <path>
```

Video files, model weights, and local configurations are intentionally excluded from the repository.

## Files Used During the Standard Video Run

The standard workflow starts three separate processes:

| Process | Files used |
|---|---|
| Video analysis | `run_video.py`, the Python modules listed below, `configs/video.local.yaml`, the video passed through `--video`, and the weights configured in `model.weights` |
| API and event management | `video_event_server.py`, the Python modules listed below, the local configuration, and generated files under `outputs/` |
| Frontend | `frontend/app/`, `frontend/public/`, `frontend/package.json`, installed dependencies, frontend build configuration, and `frontend/worker/index.ts` |

In the current local configuration, the development assets are `videos/prova4.mp4` and `yolo12n.pt`. In production mode, the frontend uses the generated build; the source files remain necessary to modify and rebuild it.

Python modules directly or indirectly required by the standard run:

- `crowd_monitor/__init__.py`
- `crowd_monitor/access_control.py`
- `crowd_monitor/analytics.py`
- `crowd_monitor/atomic_io.py`
- `crowd_monitor/config.py`
- `crowd_monitor/cv_live.py`
- `crowd_monitor/dashboard.py`
- `crowd_monitor/demo_config.py`
- `crowd_monitor/detector.py`
- `crowd_monitor/event_frames.py`
- `crowd_monitor/frontend_events.py`
- `crowd_monitor/geometry.py`
- `crowd_monitor/live_state.py`
- `crowd_monitor/presentation.py`
- `crowd_monitor/renderer.py`
- `crowd_monitor/video_pipeline.py`

The following files are generated at runtime:

- `outputs/video_events.jsonl`
- `outputs/event_status.json`
- `outputs/live_state.json`
- `outputs/live_cv.jpg`
- images under `outputs/event_frames/`

Deleting them resets event history, state, or associated images. They are generated runtime files, not unused files.

### Files Used Outside the Standard Run

- `run_realtime.py`, `crowd_monitor/pipeline.py`, `source.py`, `health.py`, and the `team_b*` modules: real-time acquisition, diagnostics, and export functionality.
- `crowd_monitor/dashboard.py`: event reader shared with the main API and still required even though the legacy dashboard was removed.
- `validate_team_b_json.py` and `crowd_monitor/cli_utils.py`: export validation and configuration loading for live execution.
- `tests/`, `docs/`, `DESIGN.md`, `UX-CONTRACT.md`, and `CHANGELOG.md`: validation and maintenance material.
- `pyproject.toml`, `.gitignore`, lockfiles, TypeScript/ESLint configuration, and YAML examples: installation, development, and repository management.

These files are not all loaded during the standard video run, but they are not unused. Removing them would remove functionality, validation, or maintenance tooling.

All four test videos are kept only in the local development environment and remain excluded from Git.

The legacy dashboard, its startup scripts, the previous editors, and separate camera preview/verification scripts were removed. The maintained interface is the current frontend together with the AI Console.
