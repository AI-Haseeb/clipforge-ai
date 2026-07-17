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
def apply_editing_style_defaults(req):  # applies the selected preset/style/value
    style = (req.editing_style or "none").strip().lower()
    preset = STYLE_PRESETS.get(style)
    if style == "none" or not preset:
        return req

    req.filter_preset = preset["filter_preset"]
    # User-selected caption controls must win over broad editing-style defaults.
    # Editing style presets filter/music only; font preset, family, size, and position stay explicit.
    req.music_enabled = preset.get("music_enabled", False)
    req.music_category = preset.get("music_category", "none")

    return req
