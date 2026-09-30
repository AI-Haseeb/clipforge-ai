# ClipForge AI

ClipForge AI is a FastAPI + Python video processing app with a static frontend for turning long videos into short-form clips. It supports transcription, highlight selection, smart reframing/cropping, captions, metadata, thumbnails, background music, and ZIP-ready exports.

## Current MVP Features

- Static frontend: `frontend/index.html`, `frontend/style.css`, `frontend/app.js`
- FastAPI backend: `backend/app/main.py`
- Video pipeline: `src/`
- Upload, project-input folder, link download, and batch upload flows
- Segment modes: Semantic AI, fixed duration, manual ranges, and raw footage
- Redis + RQ queue support for heavy background processing
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
clipforge-ai/
├─ backend/
│  └─ app/
│     ├─ main.py              # FastAPI routes, uploads, jobs, status, results, auth, music APIs
│     ├─ auth_store.py        # Local test login/signup/session storage
│     ├─ queue.py             # Redis/RQ queue helpers and queue health checks
│     ├─ worker.py            # RQ worker entrypoint for background jobs
│     ├─ job_tasks.py         # Worker-side job execution and progress updates
│     └─ __init__.py          # Python package marker
├─ frontend/
│  ├─ index.html              # Static landing page, Creator Studio, and results UI
│  ├─ style.css               # Premium dark/light responsive styling
│  ├─ app.js                  # Frontend state, upload flow, polling, and UI interactions
│  └─ assets/                 # Frontend images/icons
├─ src/
│  ├─ main.py                 # CLI pipeline entrypoint
│  ├─ pipeline/               # Audio extraction, transcription, highlights, captions, rendering
│  ├─ services/               # Pipeline runner, thumbnails, music, styles, progress helpers
│  └─ utils/                  # FFmpeg, path, logging, and license helpers
├─ assets/
│  ├─ fonts/                  # Caption fonts
│  ├─ music/                  # Background music categories
│  ├─ roman/                  # Roman caption correction data
│  └─ thumbnail_overlays/     # Thumbnail rendering assets
├─ config/
│  ├─ settings.yaml           # Main local settings
│  ├─ keywords.txt            # Highlight/metadata keywords
│  └─ *_api_key.txt           # Local-only API keys, ignored by git
├─ data/
│  ├─ input/                  # Local test videos, ignored by git except .gitkeep
│  ├─ uploads/                # Runtime uploads, ignored
│  ├─ link_uploads/           # Runtime downloaded link videos, ignored
│  ├─ work/                   # Runtime intermediate files, ignored
│  ├─ cache/                  # Transcript/cache files, ignored
│  ├─ jobs/                   # Backend job outputs, ignored
│  ├─ output/                 # CLI output, ignored
│  └─ batches/                # Batch output, ignored
├─ scripts/                   # Local run helpers
├─ tests/                     # Focused tests
├─ tools/                     # Local dev/test utilities
├─ QUEUE_SETUP.md             # Redis/RQ setup details
├─ PROJECT_STRUCTURE.md       # Project structure notes
├─ requirements.txt           # Python dependencies
└─ .gitignore                 # Keeps secrets/runtime files out of git
```

## Requirements

Install these before running the app:

- Python 3.11 recommended (Python 3.10+ should work)
- Git
- FFmpeg available in terminal as `ffmpeg` and `ffprobe`
- VS Code Live Server or any static file server for the frontend
- Docker only if you want to run Redis easily for queue mode

For a CPU-only computer, use at least 4 CPU cores and 8 GB RAM for small videos.
For regular 1080p work, 16 GB RAM is a safer baseline. A CUDA-capable NVIDIA GPU is
optional; it mainly speeds up Whisper transcription. Rendering still uses FFmpeg and
CPU resources. Keep at least 50 GB of free SSD space because uploaded videos,
intermediate files, and generated results can be large.

### Install and verify FFmpeg

FFmpeg is a system dependency and is not installed by `pip install`. On Windows,
install a trusted FFmpeg build, add its `bin` folder to PATH, then open a new
PowerShell window. With WinGet available, this is one option:

```powershell
winget install --id Gyan.FFmpeg.Shared -e
```

On macOS:

```bash
brew install ffmpeg
```

On Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

Verify the installation before starting ClipForge:

```text
ffmpeg -version
ffprobe -version
```

The checked-in settings use `ffmpeg` and `ffprobe` from PATH, so a new computer does
not need the old machine's `C:/ffmpeg/...` path.

## Download From GitHub

```powershell
git clone https://github.com/AI-Haseeb/clipforge-ai.git
cd clipforge-ai
```

For a copy-paste setup guide on a new Windows computer, open
[`START_CLIPFORGE_ON_NEW_COMPUTER.txt`](START_CLIPFORGE_ON_NEW_COMPUTER.txt).

## Setup

Create and activate a virtual environment:

```powershell
py -3.11 -m venv clipforge_env
.\clipforge_env\Scripts\Activate.ps1
pip install -r requirements.txt
```

If `py -3.11` is not available, use:

```powershell
python -m venv clipforge_env
.\clipforge_env\Scripts\Activate.ps1
pip install -r requirements.txt
```

Add local API keys only if needed:

```text
config/openai_api_key.txt
config/huggingface_api_key.txt
```

Do not commit API keys. They are ignored by `.gitignore`.

### Windows PowerShell activation

If PowerShell blocks script execution, run this exact command. Do not add an extra
closing parenthesis after `RemoteSigned`:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& ".\clipforge_env\Scripts\Activate.ps1"
```

If your environment folder has a different name, replace `clipforge_env` with that
folder name. On macOS/Linux use:

```bash
python3 -m venv clipforge_env
source clipforge_env/bin/activate
pip install -r requirements.txt
```

After installing dependencies, run the verification commands below before opening the
frontend. The first Whisper run may download a model and can take several minutes.

## Run Locally Without Queue

Start backend in Terminal 1:

```powershell
python -m uvicorn backend.app.main:app --reload
```

Open the frontend in Terminal 2 with VS Code Live Server or another static server:

```text
frontend/index.html
```

For a simple Python static server, run this from the repository root:

```powershell
python -m http.server 5500 --directory frontend
```

Then open <http://127.0.0.1:5500> in your browser. Keep the backend at
<http://127.0.0.1:8000>.

Recommended quick test:

1. Put a small video inside `data/input/`.
2. Open Creator Studio.
3. Select Project Input video.
4. Choose Manual mode for a short range, for example `0-30`.
5. Run with captions ON.
6. Check shorts, thumbnails, metadata, and ZIP in Results.

## Run With Redis + RQ Queue

Use queue mode when testing background processing.

Terminal 1, start Redis with Docker:

```powershell
docker run --name clipforge-redis -p 6379:6379 -d redis:7
```

If Redis container already exists:

```powershell
docker start clipforge-redis
```

Terminal 2, start FastAPI:

```powershell
python -m uvicorn backend.app.main:app --reload
```

Terminal 3, start worker:

```powershell
python -m backend.app.worker high default low
```

Queue health check:

```text
http://127.0.0.1:8000/queue/health
```

More details are in `QUEUE_SETUP.md`.

## YouTube publishing setup

YouTube publishing needs a Google OAuth desktop/web client configured for this app.
Keep the client JSON at `config/youtube_client_secret.json` locally and never commit it.
The refresh token is stored at `data/youtube_tokens/default.json`, which is also local
and ignored by Git. For local development, the OAuth callback is:

```text
http://localhost:8000/youtube/auth/callback
```

For a cloud deployment, replace the callback with the public HTTPS API URL and add the
same URL in Google Cloud Console. Use persistent storage for the token and generated
files; an ephemeral cloud disk will lose them after a restart.

## Run in a Linux cloud environment

Install system packages first:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg redis-server
```

Set the Linux FFmpeg paths in `config/settings.yaml` or use `ffmpeg` and `ffprobe` from
`PATH`; the checked-in Windows paths are only for the local Windows setup. Set secrets
through the cloud provider's environment/secrets settings instead of committing files:

```bash
export OPENAI_API_KEY="..."
export HF_TOKEN="..."
export REDIS_URL="redis://localhost:6379/0"
```

Start the API without development reload:

```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Start a separate worker for video processing:

```bash
python -m backend.app.worker high default low
```

For a small private MVP, one 4-vCPU/16-GB worker can run the API and worker together.
For a multi-user service, separate the API and workers, use managed Redis and PostgreSQL,
and put uploads/results in S3-compatible object storage. A GPU worker is recommended
only when transcription throughput matters; it is not required for the complete flow.

## Verification commands

Run these from the repository root after activating the environment:

```powershell
python -m py_compile backend/app/main.py src/main.py
node --check frontend/app.js
python -m unittest tests.test_roman_openai tests.test_progress_state -v
```

If the YouTube workflow tests are present in your checkout, run them too:

```powershell
python -m unittest tests.test_youtube_workflow -v
```

When testing queue mode, confirm Redis is reachable at:

```text
http://127.0.0.1:8000/queue/health
```

## Output Locations

Runtime files are created locally and are ignored by GitHub:

- Uploaded videos: `data/uploads/`
- Project input videos: `data/input/`
- Downloaded link videos: `data/link_uploads/`
- Intermediate work files: `data/work/`
- Transcript/cache files: `data/cache/`
- Completed backend jobs: `data/jobs/`
- Batch outputs: `data/batches/`
- CLI outputs: `data/output/` or `output/`

## Language And Caption Policy

- English detected by Whisper:
  - Metadata stays English.
  - Captions use source English transcript timing.
- Urdu/Hindi/Punjabi detected by Whisper:
  - Metadata becomes Roman.
  - Captions use source transcript timings and Roman cleanup.
  - Punjabi words are preserved in Roman form when possible.
- Captions use strict timing and do not intentionally appear early.
- Short stale captions are capped so one line does not remain visible across long silent or incorrect Whisper segments.

## GitHub Workflow

Use these commands when you make changes in VS Code:

```powershell
git status
git add .
git commit -m "Update ClipForge AI"
git push origin main
```

If the repo was freshly initialized and remote is missing:

```powershell
git remote add origin https://github.com/AI-Haseeb/clipforge-ai.git
git branch -M main
git push -u origin main
```

## Git Ignore Safety

The following are local/generated and ignored:

- `clipforge_env/`, `.venv/`, `venv/`
- `data/jobs/`, `data/output/`, `data/work/`, `data/uploads/`, `data/cache/`
- `data/input/*` test videos
- `output/`, `tmp/`
- API key files in `config/`
- local auth database and job registry files

Before pushing to GitHub, always check:

```powershell
git status
```

Make sure API keys, generated videos, ZIP files, and cache folders are not staged.
