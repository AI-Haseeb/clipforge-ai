from __future__ import annotations  # enables future Python language features
from typing import Dict  # adds type hint helpers

# NOTE:
# - yahan scale/crop NAHI hoga (wo cut_clip / reframe already karta hai)
# - sirf color/sharpen filters hain

FILTER_PRESETS: Dict[str, str] = {
    "None (No Filter)": "",

    "Natural Enhance (Recommended)": (
        "eq=contrast=1.08:brightness=0.02:saturation=1.10,"
        "unsharp=5:5:0.55:5:5:0.0"
    ),
    "Punchy + Clear": (
        "eq=contrast=1.18:brightness=0.01:saturation=1.12,"
        "unsharp=7:7:0.70:7:7:0.0"
    ),
    "Cool Modern": (
        "eq=contrast=1.12:brightness=0.00:saturation=1.08,"
        "colorbalance=rs=-0.02:bs=0.03,"
        "unsharp=5:5:0.55:5:5:0.0"
    ),
    "Warm Cinematic": (
        "eq=contrast=1.10:brightness=0.02:saturation=1.14,"
        "colorbalance=rs=0.03:gs=0.01:bs=-0.01,"
        "unsharp=5:5:0.55:5:5:0.0"
    ),

    # 🖤 Black & White (Mono) — SAFE (odd kernel sizes)
    "Black & White (Mono)": (
        "format=gray,"
        "eq=contrast=1.12:brightness=0.02,"
        "unsharp=5:5:0.60:5:5:0.0"
    ),
}
def get_filter_vf(name: str) -> str:  # returns a resolved value used by later code
    return FILTER_PRESETS.get(name, "")
