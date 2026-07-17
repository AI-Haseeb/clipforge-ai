# ClipForge AI Project Structure

This repo is organized so the source code can be uploaded to GitHub while large local videos, outputs, caches, and API keys stay local.

## Source Folders

| Path | Purpose |
| --- | --- |
| `backend/app/` | FastAPI server, API routes, job state, auth, music preview endpoints. |
| `frontend/` | Static frontend: landing page, Creator Studio, upload/manual ranges, progress, results. |
| `src/main.py` | Main CLI/pipeline entrypoint used by backend runner. |
| `src/pipeline/` | Core video pipeline: audio extraction, transcription helpers, segment selection, caption/ASS render, metadata, short rendering. |
| `src/services/` | Pipeline runner, thumbnail engine, music engine, style presets, progress writer, smart category inference. |
| `src/utils/` | FFmpeg and path helpers. |
| `assets/fonts/` | Caption fonts used during ASS subtitle burn. |
| `assets/music/` | Local background music categories. |
| `assets/roman/` | Roman-language support assets. |
| `assets/thumbnail_overlays/` | Local thumbnail renderer overlays/assets. |
| `config/settings.yaml` | Main local settings. Current policy: metadata is auto English/Roman by detected language. |
| `config/keywords.txt` | Highlight/metadata keywords. |
| `scripts/` | Local run helpers. |
| `tests/` | Focused test files. |
| `tools/` | Local dev utilities and test scripts. |

## Runtime Folders

| Path | Purpose | GitHub? |
| --- | --- | --- |
| `data/input/` | Local videos for testing. | Ignored except `.gitkeep` |
| `data/uploads/` | Browser upload temp files. | Ignored |
| `data/work/` | Audio/transcript/segment intermediate files. | Ignored |
| `data/cache/` | Transcript and other cache files. | Ignored |
| `data/jobs/` | Backend job outputs/results. | Ignored |
| `data/output/` | CLI output. | Ignored |
| `data/batches/` | Batch output. | Ignored |
| `tmp/` | Temporary verification files. | Ignored |
| `output/` | Old/generated output folder. | Ignored |

## Local-Only / Do Not Upload

These should remain on your PC only:

- `clipforge_env/` or `.venv/`
- `config/openai_api_key.txt`
- `config/huggingface_api_key.txt`
- `config/groq_api_key.txt` if still present locally
- `data/input/*` real test videos
- `data/jobs/*`, `data/output/*`, `data/work/*`, `data/uploads/*`, `data/cache/*`
- `data/clipforge_auth*.sqlite3`

## Current Language Policy

- English detected by Whisper -> English metadata and English captions.
- Urdu/Hindi/Punjabi detected by Whisper -> Roman metadata and Roman captions.
- Captions use original source transcript timing, not translated metadata timing.
- `captions.strict_timing: true` keeps caption start times aligned to speech.
- Short stale captions are capped to avoid one line staying onscreen too long.

## GitHub Upload Checklist

1. Keep `.gitignore` in place.
2. Do not stage API key files.
3. Do not stage `clipforge_env/`.
4. Do not stage generated `data/*` outputs or local test videos.
5. Run checks:

```powershell
node --check frontend/app.js
python -m py_compile backend/app/main.py src/main.py src/pipeline/cut_shorts.py src/services/smart_music.py
```
