# ClipForge AI

ClipForge AI is a FastAPI + Python video processing app with a static frontend for turning long videos into short-form clips. It supports transcription, highlight selection, smart reframing/cropping, captions, metadata, thumbnails, background music, and ZIP-ready exports.

## Current MVP Features

- Static frontend: `frontend/index.html`, `frontend/style.css`, `frontend/app.js`
- FastAPI backend: `backend/app/main.py`
- Video pipeline: `src/`
- Upload, project-input folder, link download, and batch upload flows
- Segment modes: Semantic AI, fixed duration, manual ranges, and raw footage
- Whisper/faster-whisper transcription with transcript cache
- Auto language policy:
  - English video -> English captions and English metadata
  - Urdu/Hindi/Punjabi video -> Roman captions and Roman metadata
- Source-timed captions: captions use original Whisper timing, so they appear when speech is active
- Smart content category inference from transcript/style for metadata tone, music, and thumbnails
- Caption presets, font assets, smart editing styles, filters, reframe/crop, music categories
- 3 thumbnails per short with OpenAI/HF/free/local fallback logic
- Results dashboard for shorts, thumbnails, metadata, files, and ZIP export

## Project Structure

```text
ClipForge AI Duplicate For Codex/
├─ backend/
│  └─ app/
│     ├─ main.py              # FastAPI routes, job status, auth, music endpoints
│     └─ auth_store.py        # Local test auth store
├─ frontend/
│  ├─ index.html              # Static Creator Studio + landing page
│  ├─ style.css               # Dark/light premium SaaS styling
│  ├─ app.js                  # Frontend state, upload flow, polling, results UI
│  └─ assets/                 # Frontend images/icons
├─ src/
│  ├─ main.py                 # CLI pipeline entrypoint
│  ├─ pipeline/               # Audio, transcription, segments, captions, metadata, render
│  ├─ services/               # Backend runner, music, thumbnails, styles, progress
│  ├─ utils/                  # FFmpeg/path helpers
│  └─ models/                 # Local model-related helpers/placeholders
├─ assets/
│  ├─ fonts/                  # Caption fonts
│  ├─ music/                  # Background music categories
│  ├─ roman/                  # Roman language assets
│  └─ thumbnail_overlays/     # Thumbnail rendering assets
├─ config/
│  ├─ settings.yaml           # Main local settings
│  ├─ keywords.txt            # Highlight/metadata keywords
│  └─ *_api_key.txt           # Local-only API keys, ignored by git
├─ data/
│  ├─ input/                  # Local test videos, ignored by git except .gitkeep
│  ├─ uploads/                # Runtime uploads, ignored
│  ├─ work/                   # Runtime intermediate files, ignored
│  ├─ cache/                  # Transcript/cache files, ignored
│  ├─ jobs/                   # Backend job outputs, ignored
│  ├─ output/                 # CLI output, ignored
│  └─ batches/                # Batch output, ignored
├─ scripts/                   # Local run helpers
├─ tests/                     # Focused tests
├─ tools/                     # Local dev/test utilities
├─ requirements.txt
└─ .gitignore
```

## Setup

1. Create a virtual environment outside git-tracked output:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Install FFmpeg and make sure `ffmpeg` / `ffprobe` are available, or update paths in `config/settings.yaml`.

3. Add local API keys only if needed:

```text
config/openai_api_key.txt
config/huggingface_api_key.txt
```

Do not commit API keys. They are ignored by `.gitignore`.

## Run Locally

Start backend:

```powershell
python -m uvicorn backend.app.main:app --reload
```

Open frontend with VS Code Live Server or any static server:

```text
frontend/index.html
```

Recommended testing flow:

1. Put a test video inside `data/input/`.
2. Open Creator Studio.
3. Select Project Input video.
4. Choose Manual mode for quick tests, for example `0-30`.
5. Run with captions ON.
6. Check output in the Results section.

## Language And Caption Policy

- English detected by Whisper:
  - Metadata stays English.
  - Captions use source English transcript timing.
- Urdu/Hindi/Punjabi detected by Whisper:
  - Metadata becomes Roman.
  - Captions use source transcript timings and Roman cleanup.
  - Punjabi words are preserved in Roman form when possible.
- Captions use strict timing and do not intentionally appear early.
- Short stale captions are capped so one line does not remain visible across long silent/incorrect Whisper segments.

## GitHub Notes

The following are local/generated and ignored:

- `clipforge_env/`, `.venv/`
- `data/jobs/`, `data/output/`, `data/work/`, `data/uploads/`, `data/cache/`
- `data/input/*` test videos
- `output/`, `tmp/`
- API key files in `config/`

Before uploading to GitHub, verify secrets are not staged.
