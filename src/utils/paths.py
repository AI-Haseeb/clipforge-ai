from pathlib import Path  # provides object-oriented file paths


# ============================================================
# Project Root Resolver (robust)
# ============================================================
def project_root() -> Path:  # returns the absolute project root directory
    """
    Finds project root by looking for key folders:
    - src/
    - config/

    Works even if script is run from subfolders.
    """
    here = Path.cwd().resolve()

    for p in [here] + list(here.parents):
        if (p / "src").exists() and (p / "config").exists():
            return p

    # fallback (last resort)
    return here


# ============================================================
# Path helper
# ============================================================
def p(*parts) -> Path:  # joins project-root path parts into one absolute Path
    """
    Join paths safely from project root
    Example: p("data", "input")
    """
    return project_root().joinpath(*parts)


# ============================================================
# Ensure required directories exist
# ============================================================
def ensure_dirs() -> None:  # creates or validates something required before continuing
    dirs = [
        p("data", "input"),

        p("data", "work", "audio"),
        p("data", "work", "transcripts"),
        p("data", "work", "segments"),
        p("data", "work", "subtitles"),

        p("data", "output", "shorts"),
        p("data", "output", "captions"),
        p("data", "output", "reports"),
        p("data", "output", "meta")

    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
