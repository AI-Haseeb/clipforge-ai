STYLE_PRESETS = {
    "none": {},
    "podcast": {
        "filter_preset": "Natural Enhance (Recommended)",
        "music_category": "podcast",
        "music_enabled": True,
    },
    "educational": {
        "filter_preset": "Natural Enhance (Recommended)",
        "music_category": "educational",
        "music_enabled": True,
    },
    "tutorial": {
        "filter_preset": "Cool Modern",
        "music_category": "tutorial",
        "music_enabled": True,
    },
    "motivational": {
        "filter_preset": "Warm Cinematic",
        "music_category": "motivational",
        "music_enabled": True,
    },
    "romantic": {
        "filter_preset": "Warm Cinematic",
        "music_category": "romantic",
        "music_enabled": True,
    },
    "sad": {
        "filter_preset": "Warm Cinematic",
        "music_category": "sad",
        "music_enabled": True,
    },
    "love": {
        "filter_preset": "Warm Cinematic",
        "music_category": "love",
        "music_enabled": True,
    },
    "business": {
        "filter_preset": "Cool Modern",
        "music_category": "business",
        "music_enabled": True,
    },
    "marketing": {
        "filter_preset": "Punchy + Clear",
        "music_category": "marketing",
        "music_enabled": True,
    },
    "gaming": {
        "filter_preset": "Punchy + Clear",
        "music_category": "gaming",
        "music_enabled": True,
    },
    "funny": {
        "filter_preset": "Punchy + Clear",
        "music_category": "funny",
        "music_enabled": True,
    },
    "meme": {
        "filter_preset": "Punchy + Clear",
        "music_category": "meme",
        "music_enabled": True,
    },
    "horror": {
        "filter_preset": "Black & White (Mono)",
        "music_category": "horror",
        "music_enabled": True,
    },
    "cinematic": {
        "filter_preset": "Warm Cinematic",
        "music_category": "cinematic",
        "music_enabled": True,
    },
    "documentary": {
        "filter_preset": "Natural Enhance (Recommended)",
        "music_category": "documentary",
        "music_enabled": True,
    },
    "news": {
        "filter_preset": "Cool Modern",
        "music_category": "news",
        "music_enabled": False,
    },
    "lifestyle": {
        "filter_preset": "Natural Enhance (Recommended)",
        "music_category": "lifestyle",
        "music_enabled": True,
    },
    "fitness": {
        "filter_preset": "Punchy + Clear",
        "music_category": "fitness",
        "music_enabled": True,
    },
}
def _has_value(options, key):
    if isinstance(options, dict):
        return key in options
    return key in getattr(options, "__dict__", {})


def _get_value(options, key, default=None):
    if isinstance(options, dict):
        return options.get(key, default)
    return getattr(options, key, default)


def _set_value(options, key, value):
    if isinstance(options, dict):
        options[key] = value
    else:
        setattr(options, key, value)


def _is_default_choice(value):
    return value is None or str(value).strip().lower() in {"", "auto", "default", "none"}


def apply_editing_style_defaults(options: dict) -> dict:  # fills only options that the user did not explicitly choose
    style = str(_get_value(options, "editing_style", "none") or "none").strip().lower()
    preset = STYLE_PRESETS.get(style)
    if style == "none" or not preset:
        return options

    if not _has_value(options, "filter_preset") or _is_default_choice(_get_value(options, "filter_preset")):
        _set_value(options, "filter_preset", preset["filter_preset"])

    if not isinstance(_get_value(options, "music_enabled"), bool):
        _set_value(options, "music_enabled", preset.get("music_enabled", False))

    music_track = str(_get_value(options, "music_track", "") or "").strip()
    category = _get_value(options, "music_category")
    category_missing_or_auto = not _has_value(options, "music_category") or category is None or str(category).strip().lower() in {"", "auto"}
    if not music_track and category_missing_or_auto:
        _set_value(options, "music_category", preset.get("music_category", "none"))

    reframe_key = "auto_reframe" if "auto_reframe" in preset else "reframe"
    if reframe_key in preset and not _has_value(options, reframe_key):
        _set_value(options, reframe_key, preset[reframe_key])

    return options
