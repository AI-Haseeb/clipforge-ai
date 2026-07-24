# ClipForge AI Project Structure Cleanup

This workspace is now organized around the FastAPI backend plus static online frontend.

## Keep For Current Online App

```text
ClipForge AI Duplicate For Codex/
  assets/                 # Fonts, music, roman data, icons, thumbnail overlays used by pipeline
  backend/
    app/main.py           # FastAPI API, job status, music endpoints, frontend integration
  config/                 # App settings, keywords, local API token files, local state
  data/                   # Local input library, uploads, job cache, generated test/output data
  frontend/
    index.html            # Main static frontend
    style.css             # Frontend styling and themes
    app.js                # Frontend logic and API calls
    assets/               # Frontend images/icons
  scripts/                # Local run helpers
  src/                    # Main video processing pipeline
    pipeline/             # Audio, transcription, highlights, captions, shorts rendering
    services/             # Music, thumbnails, progress, hooks, pipeline runner
    utils/                # Paths, ffmpeg helpers, logging, license utilities
  tests/                  # Existing test files
  tools/
    test_thumbnail_ai_models.py
  output/pdf/             # Capstone documentation PDF
  requirements.txt        # Python dependencies
  README.md
  .vscode/                # Live Server ignore settings and local editor config
```

## Moved To Review Folder

These files/folders were not deleted. They were moved here:

```text
_project_cleanup_review/cleanup_20260713_online_app/
```

Moved because they are desktop GUI/build/license/temp items, not required for the current online FastAPI + static frontend flow:

```text
desktop_gui_packaging/
  clipforge_gui.py
  ClipForgeAI.spec
  ClipForge_License_Generator.spec
  build/
  dist/
  tools/
    license_generator_gui.py
    generate_license.py
    license_server.py

old_frontend_backups/
  _old_split_index_parts/

temp_debug_files/
  tempCodeRunnerFile.py
  tempCodeRunnerFile.python
  _why_clipforge_check.png
  pdf_render_cache/
```

## Not Moved Yet

These are not core source files, but I left them in place because moving them can affect local testing or current workflow:

```text
clipforge_env/            # Local Python virtual environment. Can be recreated, but moving it breaks activated env paths.
data/output/              # Generated shorts, thumbnails, captions, reports from tests/jobs.
data/work/                # Intermediate processing files.
data/jobs/                # Job progress/status files.
data/cache/               # Transcript cache; useful to avoid slow Whisper reruns.
data/uploads/             # Uploaded/local test videos.
output/pdf/               # Your project documentation PDF for form submission.
ClipForge AI - Quick Start Guide.docx
```

## Later Cleanup Options

- If you want a smaller clean repo for deployment, exclude `clipforge_env/`, generated `data/output/`, `data/work/`, `data/jobs/`, and large test videos from deployment.
- Keep `data/input/` if you want the frontend input library to show local sample videos.
- Keep `data/cache/transcripts/` during testing because it saves a lot of transcription time.
- Keep `_project_cleanup_review/` only until you confirm nothing inside it is needed.
