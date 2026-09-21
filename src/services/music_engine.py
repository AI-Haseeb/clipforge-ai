from pathlib import Path  # provides object-oriented file paths
import random  # generates random choices and variation


SUPPORTED_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac"}

MUSIC_CATEGORY_FALLBACKS = {
    "tutorial": ["educational", "podcast", "calm"],
    "business": ["podcast", "calm", "educational"],
    "marketing": ["energetic", "motivational", "meme"],
    "cinematic": ["motivational", "calm"],
    "documentary": ["cinematic", "calm", "educational"],
    "news": ["podcast", "calm"],
    "lifestyle": ["calm", "motivational", "energetic"],
    "fitness": ["energetic", "motivational"],
    "funny": ["meme", "energetic"],
    "meme": ["funny", "energetic"],
    "gaming": ["energetic", "meme"],
    "horror": ["cinematic"],
    "motivational": ["cinematic", "energetic"],
    "romantic": ["love", "sad", "calm", "cinematic"],
    "sad": ["romantic", "love", "calm", "cinematic"],
    "love": ["romantic", "sad", "calm", "cinematic"],
    "educational": ["tutorial", "podcast", "calm"],
    "podcast": ["calm", "educational"],
}
def _tracks_for_category(base_path: Path, category: str) -> list[Path]:# lists music tracks for the selected category
    music_dir = base_path / category
    if not music_dir.exists():
        return []

    return [
        p for p in music_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO_EXTS
    ]
def pick_music_track(
    category: str,
    base_dir: str = "assets/music",
    preferred_track: str | None = None,
    selection_info: dict | None = None,
    warning_callback=None,
) -> str | None:  # chooses a requested track or records the fallback that replaces it
    category = (category or "none").strip().lower()
    preferred_clean = str(preferred_track or "").replace("\\", "/").strip("/")

    def record(selected: Path | None, selected_category: str = "") -> str | None:
        actual = selected.name if selected else ""
        substituted = bool(preferred_clean and selected and actual.casefold() != Path(preferred_clean).name.casefold())
        if selection_info is not None:
            selection_info.update({
                "music_substituted": substituted,
                "requested_music_track": preferred_clean,
                "actual_music_track": actual,
                "actual_music_category": selected_category,
            })
        if substituted:
            warning = (
                f"[music] WARNING: requested track '{preferred_clean}' was not found; "
                f"using fallback '{selected_category}/{actual}'."
            )
            print(warning, flush=True)
            if warning_callback:
                try:
                    warning_callback(warning)
                except Exception:
                    pass
        return str(selected) if selected else None

    if category == "none":
        return record(None)

    base_path = Path(base_dir)
    preferred_parts = [part for part in preferred_clean.split("/") if part]
    if preferred_parts and not any(part in {".", ".."} for part in preferred_parts):
        category_dir = (base_path / category).resolve()
        preferred_path = (category_dir / Path(*preferred_parts)).resolve()
        try:
            preferred_path.relative_to(category_dir)
        except ValueError:
            preferred_path = None
        if preferred_path and preferred_path.is_file() and preferred_path.suffix.lower() in SUPPORTED_AUDIO_EXTS:
            return record(preferred_path, category)

    search_order = [category, *MUSIC_CATEGORY_FALLBACKS.get(category, [])]
    for candidate in dict.fromkeys(search_order):
        tracks = _tracks_for_category(base_path, candidate)
        if tracks:
            return record(random.choice(tracks), candidate)

    all_tracks = [
        p for p in base_path.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO_EXTS
    ] if base_path.exists() else []

    if not all_tracks:
        return record(None)

    selected = random.choice(all_tracks)
    try:
        selected_category = selected.parent.relative_to(base_path).parts[0]
    except (ValueError, IndexError):
        selected_category = selected.parent.name
    return record(selected, selected_category)