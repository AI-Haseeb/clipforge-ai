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
def pick_music_track(category: str, base_dir: str = "assets/music", preferred_track: str | None = None) -> str | None:  # chooses a matching preset, track, or fallback
    category = (category or "none").strip().lower()

    if category == "none":
        return None

    base_path = Path(base_dir)

    preferred_clean = str(preferred_track or "").replace("\\", "/").strip("/")
    preferred_parts = [part for part in preferred_clean.split("/") if part]
    if preferred_parts and not any(part in {".", ".."} for part in preferred_parts):
        category_dir = (base_path / category).resolve()
        preferred_path = (category_dir / Path(*preferred_parts)).resolve()
        try:
            preferred_path.relative_to(category_dir)
        except ValueError:
            preferred_path = None
        if preferred_path and preferred_path.is_file() and preferred_path.suffix.lower() in SUPPORTED_AUDIO_EXTS:
            return str(preferred_path)

    search_order = [category, *MUSIC_CATEGORY_FALLBACKS.get(category, [])]

    for candidate in dict.fromkeys(search_order):
        tracks = _tracks_for_category(base_path, candidate)
        if tracks:
            return str(random.choice(tracks))

    all_tracks = [
        p for p in base_path.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO_EXTS
    ] if base_path.exists() else []

    if not all_tracks:
        return None

    return str(random.choice(all_tracks))
