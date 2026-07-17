from __future__ import annotations  # enables future Python language features
from email import parser  # parses and formats email data
from pathlib import Path  # provides object-oriented file paths
import yaml  # reads and writes YAML config data
import json  # handles JSON encode and decode
import subprocess  # runs external system commands
import re  # matches and cleans text with regular expressions
import argparse  # parses command-line arguments
import hashlib  # creates cryptographic hashes
import shutil  # copies, moves, and removes files/folders
from typing import Tuple, List, Dict, Any, Optional  # adds type hint helpers
from src.pipeline.filters import FILTER_PRESETS  # project filter presets
from src.utils.paths import ensure_dirs, p  # project path helper
from src.pipeline.extract_audio import extract  # project helper module
from src.pipeline.detect_highlights import load_keywords, pick_segments, save_segments  # project helper module
from src.pipeline.text_utils import literal_romanize  # project text cleanup helpers
from src.services.progress import set_progress  # project progress writer
from src.services.smart_music import infer_music_category  # infers content/music category from transcript and style


# ============================================================
# Language policy + helpers
# ============================================================
def _norm_lang(lang: str) -> str:# normalizes lang text/value for consistent matching
    return (lang or "").strip().lower()
def romanize_text(s: str) -> str:# converts text text into Roman letters
    """
    Urdu/Hindi script -> Roman (ASCII-ish) using Unidecode.
    Safe: if Unidecode missing, returns original.
    """
    try:
        from unidecode import unidecode as _ud  # converts Unicode text to ASCII
        return _ud(s or "")
    except Exception:
        return s or ""
def _get_plan(settings: dict) -> str:  # returns a resolved value used by later code
    plan = _norm_lang(str(settings.get("plan", "free") or "free"))
    return "paid" if plan == "paid" else "free"
def _get_ai_cfg(settings: dict) -> dict:  # returns a resolved value used by later code
    cfg = settings.get("ai_features", {}) or {}
    return cfg if isinstance(cfg, dict) else {}
def _semantic_allowed_for_lang(lang: str, settings: dict) -> bool:# handles semantic allowed for lang behavior
    lang = _norm_lang(lang)
    allowed = settings.get("semantic_languages", ["en"])
    if not isinstance(allowed, list):
        allowed = ["en"]
    allowed = [_norm_lang(x) for x in allowed if isinstance(x, str)]

    # Ã¢Å“â€¦ allow all languages
    if "*" in allowed or "all" in allowed:
        return True

    return lang in allowed
def _fallback_clip_mode_for_non_english(settings: dict) -> str:# handles fallback clip mode for non english behavior
    fb = str(settings.get("fallback_clip_mode_for_non_english", "simple_auto") or "simple_auto").strip().lower()
    if fb not in ("simple_auto", "manual"):
        fb = "simple_auto"
    return fb
def _detect_language_fast(audio_wav: Path, *, model_name: str, settings: dict) -> str:  # finds highlights, faces, language, timing, or visual signals
    """
    print("   1) Fast      -> fastest processing (testing / drafts)")
    Doesn't need full segment iteration.
    """
    try:
        from faster_whisper import WhisperModel  # runs Faster-Whisper speech recognition
        compute_type = str((settings or {}).get("whisper_compute_type", "int8"))
        wm = WhisperModel(model_name, device="cpu", compute_type=compute_type)
        _seg_iter, info = wm.transcribe(
            str(audio_wav),
            beam_size=1,
            vad_filter=True,
            word_timestamps=False,
            task="transcribe",
        )
        return _norm_lang(getattr(info, "language", "") or "")
    except Exception:
        return ""


# ============================================================
# Settings helpers
# ============================================================
def _file_hash(path: Path, chunk_size: int = 1024 * 1024) -> str:# creates a hash used for cache keys or validation
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()
def _transcript_cache_path(input_video: Path, model_name: str, task: str) -> Path:# builds the transcript/cache file path
    cache_dir = p("data", "cache", "transcripts")
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        digest = _file_hash(input_video)
    except Exception:
        stat = Path(input_video).stat()
        digest = hashlib.sha256(f"{Path(input_video).resolve()}:{stat.st_size}:{stat.st_mtime}".encode("utf-8")).hexdigest()
    clean_model = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(model_name or "whisper"))
    clean_task = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(task or "transcribe"))
    return cache_dir / f"{digest}.{clean_model}.{clean_task}.json"
def _transcribe_with_cache(whisper_mod, *, input_video: Path, audio_wav: Path, out_json: Path, model_name: str, task: str, settings: dict) -> dict:  # converts audio into timestamped transcript text
    cache_path = _transcript_cache_path(input_video, model_name, task)
    if cache_path.exists():
        print(f"[cache] Transcript cache hit ({task}): {cache_path}", flush=True)
        try:
            out_json.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cache_path, out_json)
        except Exception:
            pass
        return json.loads(cache_path.read_text(encoding="utf-8"))

    result = whisper_mod.transcribe(
        audio_wav,
        out_json,
        model_name=model_name,
        task=task,
        settings=settings,
    )
    try:
        cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[cache] Transcript saved ({task}): {cache_path}", flush=True)
    except Exception as e:
        print(f"[cache] Transcript save skipped ({task}): {e}", flush=True)
    return result
def _segment_overlap_seconds(a: dict, b: dict) -> float:# handles segment overlap seconds behavior
    a_start = float(a.get("start", 0.0) or 0.0)
    a_end = float(a.get("end", a_start) or a_start)
    b_start = float(b.get("start", 0.0) or 0.0)
    b_end = float(b.get("end", b_start) or b_start)
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))
def _best_aligned_text(source_seg: dict, translated_segments: List[dict], source_index: int) -> str:# handles best aligned text behavior
    best_text = ""
    best_overlap = 0.0
    for tr_seg in translated_segments:
        overlap = _segment_overlap_seconds(source_seg, tr_seg)
        if overlap > best_overlap:
            best_overlap = overlap
            best_text = (tr_seg.get("text") or "").strip()

    if best_text:
        return best_text

    if 0 <= source_index < len(translated_segments):
        return (translated_segments[source_index].get("text") or "").strip()
    return ""
def _build_selection_transcript(  # constructs a command, payload, prompt, caption, or response object
    *,
    source_result: dict,
    meta_result: dict,
    detected_lang: str,
    settings: dict,
) -> dict:
    """
    Urdu/Hindi selection helper.

    Keeps original source timestamps/words as the master timeline, but gives
    highlight pickers richer text for scoring:
      - original Whisper text
      - literal Roman form for Roman keyword hits
      - English translated text for semantic meaning and English keyword hits
    """
    lang = _norm_lang(detected_lang)
    if lang not in ("ur", "hi"):
        return source_result

    cfg = (settings or {}).get("non_english_selection", {}) or {}
    if isinstance(cfg, dict) and cfg.get("enabled") is False:
        return source_result

    source_segments = list((source_result or {}).get("segments") or [])
    translated_segments = list((meta_result or {}).get("segments") or [])
    if not source_segments:
        return source_result

    normalized_segments: List[dict] = []
    changed_count = 0

    for idx, seg in enumerate(source_segments):
        original = (seg.get("text") or "").strip()
        roman = literal_romanize(original).strip()
        english = _best_aligned_text(seg, translated_segments, idx)

        parts: List[str] = []
        seen = set()
        for value in (original, roman, english):
            value = re.sub(r"\s+", " ", value or "").strip()
            key = value.lower()
            if not value or key in seen:
                continue
            seen.add(key)
            parts.append(value)

        selection_text = " | ".join(parts) if parts else original
        new_seg = dict(seg)
        new_seg["original_text"] = original
        new_seg["roman_text"] = roman
        new_seg["english_text"] = english
        new_seg["selection_text"] = selection_text
        new_seg["text"] = selection_text
        normalized_segments.append(new_seg)

        if selection_text != original:
            changed_count += 1

    out = dict(source_result or {})
    out["segments"] = normalized_segments
    out["selection_mode"] = "source_timing_original_roman_english"
    out["selection_language"] = lang
    print(
        f"[Selection] Urdu/Hindi normalized transcript ready: "
        f"{changed_count}/{len(normalized_segments)} segments enriched for scoring.",
        flush=True,
    )
    return out
def load_settings() -> dict:  # loads required data/settings into memory
    cfg_path = p("config", "settings.yaml")
    if not cfg_path.exists():
        return {}
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
def save_settings(settings: dict) -> None:  # saves generated state or output files
    cfg_path = p("config", "settings.yaml")
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        yaml.safe_dump(settings, sort_keys=False, allow_unicode=True),
        encoding="utf-8"
    )


# ============================================================
# CLI helpers
# ============================================================
def ask_yes_no(prompt: str, *, default_yes: bool = True) -> bool:# asks the CLI user for the yes no option
    tag = "Y/n" if default_yes else "y/N"
    ans = input(f"   {prompt} [{tag}]: ").strip().lower()
    if not ans:
        return default_yes
    return ans in ("y", "yes", "1", "true")
def ask_select(prompt: str, *, default_key: str) -> str:# asks the CLI user for the select option
    ans = input(f"   {prompt} [{default_key}]: ").strip()
    return ans if ans else default_key
def pick_input_videos() -> list[Path]:  # chooses a matching preset, track, or fallback
    input_dir = p("data", "input")
    if not input_dir.exists():
        raise FileNotFoundError(f"Input folder missing: {input_dir}")
    exts = {".mp4", ".mov", ".mkv", ".m4v", ".webm"}
    vids = sorted([x for x in input_dir.iterdir() if x.is_file() and x.suffix.lower() in exts])
    if not vids:
        raise FileNotFoundError(f"No video found in {input_dir}. Put .mp4/.mov/.mkv there.")
    return vids
def ask_processing_preset(default_mode: str) -> str:# asks the CLI user for the processing preset option
    default_mode = (default_mode or "balanced").strip().lower()
    if default_mode not in ("fast", "balanced", "quality"):
        default_mode = "balanced"

    default_key = {"fast": "1", "balanced": "2", "quality": "3"}[default_mode]

    print("\n1) Processing Preset")
    print("   1) Fast      -> fastest processing (testing / drafts)")
    print("   2) Balanced  -> best default (recommended)")
    print("   3) Quality   -> best output (slower)")
    sel = ask_select("Select", default_key=default_key)

    return {"1": "fast", "2": "balanced", "3": "quality"}.get(sel, default_mode)
def ask_platform(default: str) -> str:# asks the CLI user for the platform option
    default = (default or "instagram").strip().lower()
    if default not in ("instagram", "tiktok", "youtube"):
        default = "instagram"

    default_key = {"instagram": "1", "tiktok": "2", "youtube": "3"}[default]

    print("\n2) Platform")
    print("   1) Instagram Reels")
    print("   2) TikTok")
    print("   3) YouTube Shorts")
    sel = ask_select("Select", default_key=default_key)

    return {"1": "instagram", "2": "tiktok", "3": "youtube"}.get(sel, default)
def ask_aspect_ratio(default_ratio: str):# asks the CLI user for the aspect ratio option
    options = {
        "1": ("9:16", 1080, 1920),
        "2": ("16:9", 1920, 1080),
        "3": ("1:1", 1080, 1080),
        "4": ("4:5", 1080, 1350),
    }
    ratio_to_key = {"9:16": "1", "16:9": "2", "1:1": "3", "4:5": "4"}
    default_key = ratio_to_key.get(default_ratio, "1")

    print("\n3) Aspect Ratio / Canvas")
    print("   1) 9:16  (1080x1920)  Shorts/Reels/TikTok")
    print("   2) 16:9  (1920x1080)  YouTube Wide")
    print("   3) 1:1   (1080x1080)  Square")
    print("   4) 4:5   (1080x1350)  Instagram Feed")
    sel = ask_select("Select", default_key=default_key)

    return options.get(sel, options[default_key])
def ask_clip_mode(default_mode: str = "semantic") -> str:# asks the CLI user for the clip mode option
    default_mode = (default_mode or "semantic").strip().lower()
    if default_mode not in ("semantic", "manual", "simple_auto"):
        default_mode = "semantic"

    default_key = {"semantic": "1", "manual": "2", "simple_auto": "3"}[default_mode]

    print("\n4) Clip Selection")
    print("   1) Semantic (AI selects best moments)   [PAID]")
    print("   2) Manual   (custom time ranges)")
    print("   3) Simple Auto (rule-based)             [FREE]")
    sel = ask_select("Select", default_key=default_key)

    return {"1": "semantic", "2": "manual", "3": "simple_auto"}.get(sel, default_mode)
def ask_filter_preset(default_name: str) -> str:# asks the CLI user for the filter preset option
    names = list(FILTER_PRESETS.keys())
    if default_name not in names:
        default_name = "Natural Enhance (Recommended)"

    print("\nFilter Preset")
    for idx, n in enumerate(names, start=1):
        print(f"   {idx}) {n}")

    choice = input(f"   Select (1-{len(names)}) or Enter for default [{default_name}]: ").strip()
    if not choice:
        return default_name
    if choice.isdigit():
        i = int(choice)
        if 1 <= i <= len(names):
            return names[i - 1]
    return default_name


# ============================================================
# Time parsing + ffprobe duration
# ============================================================
def _parse_time_to_seconds(s: str) -> float:  # turns raw text/API data into structured values
    s = (s or "").strip().lower()
    if not s:
        raise ValueError("empty time")

    m = re.fullmatch(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?", s)
    if m and (m.group(1) or m.group(2) or m.group(3)):
        hh = float(m.group(1) or 0)
        mm = float(m.group(2) or 0)
        ss = float(m.group(3) or 0)
        return hh * 3600 + mm * 60 + ss

    if ":" in s:
        parts = [p.strip() for p in s.split(":") if p.strip() != ""]
        if len(parts) == 2:
            mm, ss = parts
            return float(mm) * 60 + float(ss)
        if len(parts) == 3:
            hh, mm, ss = parts
            return float(hh) * 3600 + float(mm) * 60 + float(ss)

    return float(s)
def _ffprobe_duration_seconds(ffprobe_path: str, video: Path) -> float:# reads video metadata with FFprobe
    cmd = [
        ffprobe_path, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(video),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "").strip() or "ffprobe failed")
    data = json.loads(proc.stdout or "{}")
    dur = float(data.get("format", {}).get("duration", 0.0) or 0.0)
    return max(0.0, dur)
def _segments_from_manual(# builds clip segment data for segments from manual
    *,
    video_duration: float,
    max_shorts: int,
    ranges_str: Optional[str] = None,
) -> list[dict]:
    """
    Manual segments.

    If ranges_str is provided (e.g. '0:10-0:30;1:00-1:20'), parse and return
    without interactive prompts (for GUI / --silent).
    Otherwise fall back to interactive questions.
    """
    # Non-interactive path (used by GUI)
    if ranges_str:
        segs: list[dict] = []
        raw_ranges = [r.strip() for r in re.split(r"[;,]", ranges_str) if r.strip()]
        for rng in raw_ranges:
            if "-" not in rng:
                continue
            a, b = [x.strip() for x in rng.split("-", 1)]
            try:
                start = _parse_time_to_seconds(a)
                end = _parse_time_to_seconds(b)
                if end <= start:
                    continue

                start = max(0.0, min(start, video_duration))
                end = max(0.0, min(end, video_duration))
                if end <= start:
                    continue

                segs.append({"start": start, "end": end, "text": ""})
                if len(segs) >= max_shorts:
                    break
            except Exception:
                continue
        return segs

    # ---------- Original interactive mode ----------
    print("\nManual mode:")
    print("Time format examples: 75 | 01:15 | 00:01:15 | 1m15s")

    n_raw = input(f"How many clips? (max {max_shorts}): ").strip()
    try:
        n = int(n_raw)
    except Exception:
        n = 1
    n = max(1, min(max_shorts, n))

    segs: list[dict] = []
    for i in range(1, n + 1):
        while True:
            rng = input(f"Clip {i} time range (start-end): ").strip()
            if "-" not in rng:
                print("ERROR: Use start-end (example: 10-25 or 00:10-00:25)")
                continue

            a, b = [x.strip() for x in rng.split("-", 1)]
            try:
                start = _parse_time_to_seconds(a)
                end = _parse_time_to_seconds(b)
                if end <= start:
                    print("ERROR: end must be greater than start")
                    continue

                start = max(0.0, min(start, video_duration))
                end = max(0.0, min(end, video_duration))
                if end <= start:
                    print("ERROR: range out of bounds after clamp")
                    continue

                segs.append({"start": start, "end": end, "text": ""})
                break
            except Exception as e:
                print(f"ERROR: Invalid time: {e}")
                continue

    return segs
def _segments_from_simple_auto(# builds clip segment data for segments from simple auto
    *,
    whisper_result: dict,
    video_duration: float,
    min_len: int,
    max_len: int,
    max_shorts: int,
    detected_lang: str = "",
    settings: Optional[dict] = None,
    simple_auto_mode: Optional[str] = None,
    simple_auto_chunk_len: Optional[float] = None,
    simple_auto_gap_thr: Optional[float] = None,
    interactive: bool = True,
) -> list[dict]:
    settings = settings or {}
    lang = _norm_lang(detected_lang)

    # default gap per-language
    default_gap = 0.45
    if lang in ("ur", "hi"):
        default_gap = float(settings.get("simple_auto_gap_ur_hi", 0.60) or 0.60)
    else:
        default_gap = float(settings.get("simple_auto_gap_default", 0.45) or 0.45)

    mode = (simple_auto_mode or "").strip().lower()

    # ----- Helper: uniform chunking -----
    def _uniform_chunks(chunk_len: float) -> list[dict]:# handles uniform chunks behavior
        segs: list[dict] = []
        t = 0.0
        while t < video_duration and len(segs) < max_shorts:
            start = t
            end = min(video_duration, t + chunk_len)
            if (end - start) >= float(min_len):
                segs.append({"start": start, "end": end, "text": ""})
            t = end
        return segs

    # ----- Helper: silence-based -----
    def _silence_based(gap_thr: float) -> list[dict]:# handles silence based behavior
        speech: List[Tuple[float, float]] = []
        for seg in whisper_result.get("segments", []) or []:
            s = float(seg.get("start", 0.0) or 0.0)
            e = float(seg.get("end", 0.0) or 0.0)
            if e > s:
                speech.append((s, e))
        speech.sort(key=lambda x: x[0])

        if not speech:
            # fallback uniform if no speech segments
            return _uniform_chunks(float(max_len))

        merged: List[Tuple[float, float]] = []
        cur_s, cur_e = speech[0]
        for s, e in speech[1:]:
            if (s - cur_e) < gap_thr:
                cur_e = max(cur_e, e)
            else:
                merged.append((cur_s, cur_e))
                cur_s, cur_e = s, e
        merged.append((cur_s, cur_e))

        segs: list[dict] = []
        for s, e in merged:
            dur = e - s
            if dur < float(min_len):
                continue

            if dur > float(max_len):
                t = s
                while t < e and len(segs) < max_shorts:
                    ss = t
                    ee = min(e, t + float(max_len))
                    if (ee - ss) >= float(min_len):
                        segs.append({"start": ss, "end": ee, "text": ""})
                    t = ee
            else:
                segs.append({"start": s, "end": e, "text": ""})

            if len(segs) >= max_shorts:
                break

        return segs[:max_shorts]

    # ---------- Non-interactive path (GUI / --silent) ----------
    if not interactive and mode in ("uniform", "silence"):
        if mode == "uniform":
            try:
                chunk_len = float(simple_auto_chunk_len or max_len)
            except Exception:
                chunk_len = float(max_len)
            chunk_len = max(float(min_len), min(float(max_len), chunk_len))
            return _uniform_chunks(chunk_len)

        # silence-based
        try:
            gap_thr = float(simple_auto_gap_thr or default_gap)
        except Exception:
            gap_thr = float(default_gap)
        return _silence_based(gap_thr)

    # ---------- Original interactive mode ----------
    print("\nSimple Auto mode:")
    print("1) Uniform chunks (equal parts)")
    print("2) Silence-based (speech blocks)")
    choice = input("Select (1-2) or Enter for default [1]: ").strip() or "1"

    if choice == "1":
        chunk_raw = input(f"Chunk length seconds? (default {max_len}): ").strip()
        try:
            chunk_len = float(chunk_raw) if chunk_raw else float(max_len)
        except Exception:
            chunk_len = float(max_len)

        chunk_len = max(float(min_len), min(float(max_len), chunk_len))
        return _uniform_chunks(chunk_len)

    gap_raw = input(f"Silence gap threshold seconds? (default {default_gap}): ").strip()
    try:
        gap_thr = float(gap_raw) if gap_raw else float(default_gap)
    except Exception:
        gap_thr = float(default_gap)

    return _silence_based(gap_thr)



# ============================================================
# Tool path helpers
# ============================================================
def _resolve_tool_path(settings_val: str, fallback: str) -> str:  # converts settings/input into a concrete path or option
    cand = (settings_val or "").strip()
    if cand:
        try:
            pth = Path(cand)
            if pth.is_absolute() and pth.exists():
                return str(pth)
        except Exception:
            pass

    try:
        fp = Path(fallback)
        if fp.is_absolute() and fp.exists():
            return str(fp)
    except Exception:
        pass

    return cand or fallback
def _validate_tool_exists(label: str, tool: str) -> None:# validates tool exists before continuing
    tp = Path(tool)
    if tp.is_absolute() and not tp.exists():
        raise FileNotFoundError(f"{label} not found at: {tool}")


# ============================================================
# CLI args
# ============================================================
def _parse_args() -> argparse.Namespace:  # turns raw text/API data into structured values
    ap = argparse.ArgumentParser(prog="clipforge")
    ap.add_argument("--silent", action="store_true", help="Run using settings.yaml only (no prompts).")
    ap.add_argument("--interactive", action="store_true", help="Force interactive prompts (default behavior).")
    ap.add_argument("--once", action="store_true", help="After interactive run, save choices back to settings.yaml.")
    ap.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
    ap.add_argument("--reframe", choices=["on", "off"], default=None, help="Override reframe for this run only.")
    ap.add_argument("--burn-debug", action="store_true", help="Print extra debug info (Whisper tracks).")

    # ---- NEW: overrides for GUI / CLI automation ----
    ap.add_argument("--plan", dest="plan_override", choices=["free", "paid", "pro"],
                    help="Override plan for this run (free/paid/pro).")
    ap.add_argument("--platform", dest="platform_override",
                    help="Override platform preset (youtube/instagram/tiktok).")
    ap.add_argument("--aspect", dest="aspect_override",
                    choices=["9:16", "16:9", "1:1", "4:5"],
                    help="Override aspect ratio/canvas.")
    ap.add_argument("--output-resolution", dest="output_resolution",
                    choices=["1080p", "720p", "480p"], default="1080p",
                    help="Override output video resolution/quality.")
    ap.add_argument("--filter-preset", dest="filter_preset_override",
                    help="Override color/filter preset.")
    ap.add_argument("--font-preset",dest="font_preset_override",
                    choices=["clean_white","bold_yellow","podcast_blue","gaming_neon","horror_red","meme_big","viral_dynamic","creator_pop","scroll_stopper","soft_glow",],
                    help="Override caption font preset.")
    ap.add_argument(
        "--caption-position",
        dest="caption_position_override",
        choices=["bottom_center", "center", "top_center"],
        help="Override caption position.")

    ap.add_argument(
        "--caption-size",
        dest="caption_size_override",
        choices=["extra_small", "small", "medium", "large", "extra_large"],
        help="Override caption size."
    )

    ap.add_argument(
        "--font-family",
        dest="font_family_override",
        choices=["preset", "Montserrat", "Poppins", "Raleway", "Anton", "Bebas Neue", "Oswald", "Archivo Black", "Luckiest Guy", "Fredoka"],
        help="Override caption font family."
    )

    ap.add_argument(
        "--caption-case",
        dest="caption_case_override",
        choices=["preset", "normal", "uppercase", "lowercase"],
        help="Override caption letter case."
    )

    ap.add_argument(
        "--music-enabled",
        dest="music_enabled_override",
        choices=["on", "off"],
        help="Enable or disable background music."
    )

    ap.add_argument(
        "--music-category",
        dest="music_category_override",
        choices=[
            "none",
            "auto",
            "podcast",
            "educational",
            "tutorial",
            "motivational",
            "romantic",
            "sad",
            "love",
            "business",
            "marketing",
            "gaming",
            "funny",
            "meme",
            "horror",
            "cinematic",
            "documentary",
            "news",
            "lifestyle",
            "fitness",
            "calm",
            "energetic",
        ],
        help="Background music category."
    )

    ap.add_argument(
        "--editing-style",
        dest="editing_style_override",
        help="Selected editing style, used by smart auto music selection."
    )

    ap.add_argument(
        "--music-volume",
        dest="music_volume_override",
        type=float,
        help="Background music volume. Example: 0.20 = 20 percent."
    )    

    ap.add_argument(
        "--music-track",
        dest="music_track_override",
        help="Preferred background music filename from the selected category."
    )



    ap.add_argument("--segment-mode", dest="segment_mode",
                    choices=["semantic_ai", "rule_chunks", "manual"],
                    help="Clip selection mode for this run.")

    ap.add_argument("--input", dest="single_input",
                    help="Process only this video file instead of data/input folder.")
    ap.add_argument("--out-dir", dest="out_dir_base",
                    help="Base output folder (shorts/meta/reports).")

    ap.add_argument("--captions", action="store_true", help="Enable captions for this run.")
    ap.add_argument("--no-captions", action="store_true", help="Disable captions for this run.")
    ap.add_argument("--roman-captions", action="store_true",
                    help="Prefer Roman captions for Urdu/Hindi (paid plan only).")
    ap.add_argument("--ai-meta", action="store_true", help="Enable AI hooks & metadata.")
    ap.add_argument("--no-ai-meta", action="store_true", help="Disable AI hooks & metadata.")

    # Rule-based chunks / manual ranges
    ap.add_argument("--simple-auto-mode", choices=["uniform", "silence"],
                    help="Rule-based chunks: uniform or silence-based.")
    ap.add_argument("--simple-auto-chunk-len", type=float,
                    help="Uniform chunk length in seconds (simple auto).")
    ap.add_argument("--simple-auto-gap-thr", type=float,
                    help="Silence gap threshold in seconds (simple auto).")
    ap.add_argument("--manual-ranges", type=str,
                    help="Manual clip ranges, e.g. '0:10-0:30;1:00-1:20'.")


    return ap.parse_args()


# ============================================================
# MAIN
# ============================================================
def main():  # runs this module as its command-line entry point
    args = _parse_args()

    ensure_dirs()
    settings = load_settings()

    # ---------- CLI overrides from GUI / automation ----------
    # Plan override
    if getattr(args, "plan_override", None):
        plan_cli = args.plan_override.strip().lower()
        if plan_cli == "pro":
            plan_cli = "paid"
        settings["plan"] = plan_cli

    # Platform override
    if getattr(args, "platform_override", None):
        plat = args.platform_override.strip().lower()
        if plat in ("youtube", "youtube_shorts"):
            settings["platform_default"] = "youtube"
        elif plat in ("instagram", "instagram_reels"):
            settings["platform_default"] = "instagram"
        elif plat in ("tiktok",):
            settings["platform_default"] = "tiktok"

    # Aspect override
    if getattr(args, "aspect_override", None):
        settings["aspect_ratio_default"] = args.aspect_override.strip()

    if getattr(args, "filter_preset_override", None):
        fp = args.filter_preset_override.strip()
        settings["filter_preset_default"] = fp
        settings["filters_enabled"] = (fp != "None (No Filter)")
        
    FONT_PRESETS = {
        "clean_white": {
            "text_case": "uppercase",
            "font_name": "Montserrat",
            "font_size": 41,
            "margin_v": 180,
            "margin_l": 90,
            "outline": 3,
            "letter_spacing": 9,
            "italic": False,
            "bold": 0,
            "shadow": 0,
            "primary_color": "&H00FFFFFF",
            "outline_color": "&H00000000",
            "back_color": "&H64000000",
            "glow_color": "&H00FFFFFF",
            "glow_blur": 2,
        },
        "bold_yellow": {
            "text_case": "uppercase",
            "font_name": "Montserrat",
            "font_size": 48,
            "margin_v": 170,
            "margin_l": 90,
            "outline": 4,
            "letter_spacing": 10,
            "italic": False,
            "bold": -1,
            "shadow": 1,
            "primary_color": "&H00FFFFFF",
            "accent_color": "&H0000FFFF",
            "accent_mode": "last_line",
            "outline_color": "&H00000000",
            "back_color": "&H64000000",
            "glow_color": "&H0000FFFF",
            "glow_blur": 7,
        },
        "podcast_blue": {
            "text_case": "uppercase",
            "font_name": "Montserrat",
            "font_size": 44,
            "margin_v": 185,
            "margin_l": 90,
            "outline": 4,
            "letter_spacing": 8,
            "italic": False,
            "bold": -1,
            "shadow": 1,
            "primary_color": "&H00FFFFFF",
            "accent_color": "&H00FFAA33",
            "accent_mode": "last_line",
            "outline_color": "&H00000000",
            "back_color": "&H64000000",
            "glow_color": "&H00FFAA33",
            "glow_blur": 7,
        },
        "gaming_neon": {
            "text_case": "uppercase",
            "font_name": "Montserrat",
            "font_size": 50,
            "margin_v": 150,
            "margin_l": 80,
            "outline": 5,
            "letter_spacing": 11,
            "italic": False,
            "bold": -1,
            "shadow": 2,
            "primary_color": "&H00FFFFFF",
            "accent_color": "&H0000FF00",
            "accent_mode": "last_line",
            "outline_color": "&H00000000",
            "back_color": "&H64000000",
            "glow_color": "&H0000FF00",
            "glow_blur": 8,
        },
        "horror_red": {
            "text_case": "uppercase",
            "font_name": "Montserrat",
            "font_size": 48,
            "margin_v": 170,
            "margin_l": 90,
            "outline": 5,
            "letter_spacing": 12,
            "italic": True,
            "bold": -1,
            "shadow": 2,
            "primary_color": "&H00FFFFFF",
            "accent_color": "&H000000FF",
            "accent_mode": "last_line",
            "outline_color": "&H00000000",
            "back_color": "&H64000000",
            "glow_color": "&H000000FF",
            "glow_blur": 8,
        },
        "meme_big": {
            "text_case": "uppercase",
            "font_name": "Montserrat",
            "font_size": 58,
            "margin_v": 145,
            "margin_l": 70,
            "outline": 6,
            "letter_spacing": 10,
            "italic": False,
            "bold": -1,
            "shadow": 1,
            "primary_color": "&H00FFFFFF",
            "outline_color": "&H00000000",
            "back_color": "&H64000000",
            "glow_color": "&H00FFFFFF",
            "glow_blur": 4,
        },
        "viral_dynamic": {
            "text_case": "uppercase",
            "font_name": "Poppins",
            "font_size": 48,
            "margin_v": 160,
            "margin_l": 80,
            "outline": 4,
            "letter_spacing": 8,
            "italic": False,
            "bold": -1,
            "shadow": 1,
            "primary_color": "&H00FFFFFF",
            "accent_color": "&H00FFFF00",
            "accent_mode": "last_line",
            "outline_color": "&H00000000",
            "back_color": "&H64000000",
            "glow_color": "&H00FFFF00",
            "glow_blur": 7,
            "word_dynamic": False,
        },
        "creator_pop": {
            "text_case": "uppercase",
            "font_name": "Poppins",
            "font_size": 52,
            "margin_v": 165,
            "margin_l": 78,
            "outline": 5,
            "letter_spacing": 6,
            "italic": False,
            "bold": -1,
            "shadow": 1,
            "primary_color": "&H00FFFFFF",
            "accent_color": "&H0050E66B",
            "accent_mode": "last_line",
            "outline_color": "&H00000000",
            "back_color": "&H64000000",
            "glow_color": "&H0050E66B",
            "glow_blur": 8,
        },
        "scroll_stopper": {
            "text_case": "uppercase",
            "font_name": "Montserrat",
            "font_size": 56,
            "margin_v": 145,
            "margin_l": 70,
            "outline": 6,
            "letter_spacing": 7,
            "italic": False,
            "bold": -1,
            "shadow": 2,
            "primary_color": "&H00FFFFFF",
            "accent_color": "&H0000D7FF",
            "accent_mode": "last_line",
            "outline_color": "&H00000000",
            "back_color": "&H64000000",
            "glow_color": "&H0000D7FF",
            "glow_blur": 8,
        },
        "soft_glow": {
            "text_case": "lowercase",
            "font_name": "Raleway",
            "font_size": 46,
            "margin_v": 175,
            "margin_l": 88,
            "outline": 4,
            "letter_spacing": 5,
            "italic": False,
            "bold": -1,
            "shadow": 1,
            "primary_color": "&H00FFFFFF",
            "accent_color": "&H00F9D67C",
            "accent_mode": "last_line",
            "outline_color": "&H00241405",
            "back_color": "&H64000000",
            "glow_color": "&H00F9D67C",
            "glow_blur": 8,
        },
    }

    if getattr(args, "font_preset_override", None):
        selected_font = args.font_preset_override.strip()
        settings["font_preset_selected"] = selected_font
        settings["caption_style"] = FONT_PRESETS.get(
            selected_font,
            FONT_PRESETS["clean_white"]
        )



 

    if getattr(args, "caption_position_override", None):
        selected_position = args.caption_position_override.strip()

        settings.setdefault("caption_style", {})

        if selected_position == "bottom_center":
            settings["caption_style"]["alignment"] = 2
            settings["caption_style"]["margin_v"] = 180

        elif selected_position == "center":
            settings["caption_style"]["alignment"] = 5
            settings["caption_style"]["margin_v"] = 0

        elif selected_position == "top_center":
            settings["caption_style"]["alignment"] = 8
            settings["caption_style"]["margin_v"] = 120

        settings["caption_position_selected"] = selected_position

    if getattr(args, "caption_size_override", None):
        selected_size = args.caption_size_override.strip()

        settings.setdefault("caption_style", {})

        size_map = {
            "extra_small": 28,
            "small": 34,
            "medium": 42,
            "large": 52,
            "extra_large": 62,
        }

        settings["caption_style"]["font_size"] = size_map.get(selected_size, 42)
        settings["caption_size_selected"] = selected_size    

    if getattr(args, "font_family_override", None):
        selected_family = args.font_family_override.strip()

        if selected_family != "preset":
            settings.setdefault("caption_style", {})
            settings["caption_style"]["font_name"] = selected_family
        settings["font_family_selected"] = selected_family

    if getattr(args, "caption_case_override", None):
        selected_case = args.caption_case_override.strip().lower()
        preset_case = str(settings.get("caption_style", {}).get("text_case", "normal") or "normal").lower()
        resolved_case = preset_case if selected_case == "preset" else selected_case
        if resolved_case not in ("normal", "uppercase", "lowercase"):
            resolved_case = "normal"
        settings.setdefault("captions", {})
        settings["captions"]["text_case"] = resolved_case
        settings["caption_case_selected"] = selected_case

    if getattr(args, "music_enabled_override", None):
        settings["music_enabled"] = (
            args.music_enabled_override.strip().lower() == "on"
        )

    if getattr(args, "music_category_override", None):
        settings["music_category"] = args.music_category_override.strip().lower()

    if getattr(args, "editing_style_override", None):
        settings["editing_style_selected"] = args.editing_style_override.strip().lower()

    if getattr(args, "music_volume_override", None) is not None:
        mv = float(args.music_volume_override)
        mv = max(0.0, min(1.0, mv))
        settings["music_volume"] = mv

    if getattr(args, "music_track_override", None):
        clean_track = str(args.music_track_override or "").replace("\\", "/").strip("/")
        track_parts = [part for part in clean_track.split("/") if part]
        if track_parts and not any(part in {".", ".."} for part in track_parts):
            settings["music_track"] = "/".join(track_parts)

    # Segment mode override
    if getattr(args, "segment_mode", None):
        sm = args.segment_mode
        if sm == "semantic_ai":
            settings["clip_mode_default"] = "semantic"
        elif sm == "rule_chunks":
            settings["clip_mode_default"] = "simple_auto"
        elif sm == "manual":
            settings["clip_mode_default"] = "manual"

    # Captions / Roman / AI meta overrides
    caption_cfg = settings.get("captions", {}) or {}
    if getattr(args, "captions", False):
        caption_cfg["enabled"] = True
    if getattr(args, "no_captions", False):
        caption_cfg["enabled"] = False
    settings["captions"] = caption_cfg

    if getattr(args, "roman_captions", False):
        settings["captions_roman_enabled"] = True

    ai_cfg_raw = settings.get("ai_features", {}) or {}
    if getattr(args, "ai_meta", False):
        ai_cfg_raw["enhance_meta"] = True
        ai_cfg_raw["enabled"] = True
    if getattr(args, "no_ai_meta", False):
        ai_cfg_raw["enhance_meta"] = False
    settings["ai_features"] = ai_cfg_raw

    # ---------- Now compute plan / ai_enabled ----------
    plan = _get_plan(settings)
    ai_cfg = _get_ai_cfg(settings)
    ai_enabled = (plan == "paid") and bool(ai_cfg.get("enabled", False))

    # Decide mode:
    interactive = True
    if args.silent:
        interactive = False
    if args.interactive:
        interactive = True


    # --------------------------------------------------------
    # Reframe (face center) Ã¢â‚¬â€ plan based + optional CLI override
    #
    #   FREE plan  Ã¢â€ â€™ reframe OFF (locked)
    #   PAID / PRO Ã¢â€ â€™ reframe ON  (default)
    #   --reframe on/off still allowed for advanced CLI users.
    # --------------------------------------------------------
    reframe_cfg = settings.get("reframe", {}) or {}
    reframe_kind = str(reframe_cfg.get("kind", "talking_head"))

    # Plan-based default
    if plan == "paid":
        # Pro / Paid Ã¢â€ â€™ default ON
        reframe_enabled = True
    else:
        # Free Ã¢â€ â€™ default OFF
        reframe_enabled = False

    # If settings have explicit flag, only respect it for paid plan
    if plan == "paid" and "enabled" in reframe_cfg:
        reframe_enabled = bool(reframe_cfg.get("enabled", True))

    # CLI override (for manual runs, GUI normally doesn't use this)
    if args.reframe == "on":
        reframe_enabled = True
    elif args.reframe == "off":
        reframe_enabled = False


    encode_cfg = settings.get("ffmpeg_encode", None)
    if not isinstance(encode_cfg, dict):
        encode_cfg = None

    ffmpeg_path_setting = str(settings.get("ffmpeg_path", "") or "").strip()
    ffprobe_path_setting = str(settings.get("ffprobe_path", "") or "").strip()

    ffmpeg_path = _resolve_tool_path(ffmpeg_path_setting, "C:/ffmpeg/bin/ffmpeg.exe")
    ffprobe_path = _resolve_tool_path(ffprobe_path_setting, "C:/ffmpeg/bin/ffprobe.exe")

    _validate_tool_exists("ffmpeg", ffmpeg_path)
    _validate_tool_exists("ffprobe", ffprobe_path)

    # Inputs
    if getattr(args, "single_input", None):
        inp = Path(args.single_input)
        if not inp.is_file():
            raise FileNotFoundError(f"Input video not found: {inp}")
        input_videos = [inp]
    else:
        input_videos = pick_input_videos()

    keywords_basic = load_keywords(p("config", "keywords.txt"))

    # ----------------------------
    # Run config
    # ----------------------------
    if interactive:
        print("\n" + "=" * 72)
        print("ClipForge AI - Interactive Setup")
        print("=" * 72)

        preset = ask_processing_preset(str(settings.get("processing_preset", "balanced")))
        output_quality = preset
        filters_default = True
        model_name = "small"

        platform = ask_platform(str(settings.get("platform_default", "youtube")))
        default_ratio = str(settings.get("aspect_ratio_default", "9:16"))
        mode = str(settings.get("resize_mode", "crop"))
        ratio, out_w, out_h = ask_aspect_ratio(default_ratio)

        clip_mode = ask_clip_mode(str(settings.get("clip_mode_default", "semantic")))

        print("\n5) Visual Style")
        filters_enabled = ask_yes_no(
            "Enable color/filter preset?",
            default_yes=bool(settings.get("filters_enabled", filters_default)),
        )

        filter_preset = str(settings.get("filter_preset_default", "Natural Enhance (Recommended)"))
        if filters_enabled:
            filter_preset = ask_filter_preset(filter_preset)
        else:
            filter_preset = "None (No Filter)"

        min_len = int(settings.get("short_min_seconds", 25))
        max_len = int(settings.get("short_max_seconds", 55))
        max_shorts = int(settings.get("max_shorts", 10))

        if args.once:
            settings["processing_preset"] = preset
            settings["platform_default"] = platform
            settings["aspect_ratio_default"] = ratio
            settings["resize_mode"] = mode
            settings["clip_mode_default"] = clip_mode
            settings["filters_enabled"] = bool(filters_enabled)
            settings["filter_preset_default"] = filter_preset
            settings.setdefault("reframe", {})
            settings["reframe"]["enabled"] = bool(reframe_enabled)
            settings["reframe"]["kind"] = reframe_kind
            settings["ffmpeg_path"] = ffmpeg_path
            settings["ffprobe_path"] = ffprobe_path
            save_settings(settings)
            print("\nSaved your choices to config/settings.yaml (one-time setup complete).")

    else:
        preset = str(settings.get("processing_preset", "balanced") or "balanced").strip().lower()
        if preset not in ("fast", "balanced", "quality"):
            preset = "balanced"
        output_quality = preset
        filters_default = True
        model_name = "small"

        platform = str(settings.get("platform_default", "youtube")).strip().lower()
        default_ratio = str(settings.get("aspect_ratio_default", "9:16"))
        mode = str(settings.get("resize_mode", "crop"))

        ratio_map_by_resolution = {
            "1080p": {
                "9:16": (1080, 1920),
                "16:9": (1920, 1080),
                "1:1": (1080, 1080),
                "4:5": (1080, 1350),
            },
            "720p": {
                "9:16": (720, 1280),
                "16:9": (1280, 720),
                "1:1": (720, 720),
                "4:5": (720, 900),
            },
            "480p": {
                "9:16": (480, 854),
                "16:9": (854, 480),
                "1:1": (480, 480),
                "4:5": (480, 600),
            },
        }
        output_resolution = str(getattr(args, "output_resolution", "1080p") or "1080p").strip().lower()
        if output_resolution not in ratio_map_by_resolution:
            output_resolution = "1080p"
        out_w, out_h = ratio_map_by_resolution[output_resolution].get(default_ratio, (1080, 1920))
        ratio = default_ratio

        clip_mode = str(settings.get("clip_mode_default", "semantic")).strip().lower()
        filters_enabled = bool(settings.get("filters_enabled", filters_default))
        filter_preset = str(settings.get("filter_preset_default", "Natural Enhance (Recommended)"))
        if not filters_enabled:
            filter_preset = "None (No Filter)"

        min_len = int(settings.get("short_min_seconds", 25))
        max_len = int(settings.get("short_max_seconds", 55))
        max_shorts = int(settings.get("max_shorts", 10))
    # ------------------------------------------------------------
    # Captions config (auto EN / Roman, bias from settings)
    # ------------------------------------------------------------
    caption_cfg = settings.get("captions", {}) or {}
    captions_enabled = bool(caption_cfg.get("enabled", True))
    caption_text_case = str(caption_cfg.get("text_case", "uppercase" if caption_cfg.get("uppercase", False) else "normal") or "normal").strip().lower()
    if caption_text_case not in ("normal", "uppercase", "lowercase"):
        caption_text_case = "normal"
    caption_uppercase = caption_text_case == "uppercase"
    caption_italic = bool(caption_cfg.get("italic", False))
    try:
        caption_start_bias_sec = float(caption_cfg.get("start_bias_sec", 0.0))
    except Exception:
        caption_start_bias_sec = 0.0
    captions_strict_timing = bool(caption_cfg.get("strict_timing", True))
    captions_translate_whisper = bool(settings.get("captions_translate_whisper", True))
    

    # Meta style (report) - actual romanization cut_shorts me hoti hai
    final_meta_style = str(settings.get("meta_output_style", "en") or "en").strip().lower()
    if final_meta_style not in ("en", "roman", "auto"):
        final_meta_style = "auto"

    clip_mode_label = {
        "semantic": "Semantic (AI)",
        "manual": "Manual",
        "simple_auto": "Simple Auto",
    }.get(clip_mode, clip_mode)

    print("\n" + "=" * 72)
    print("[OK] CLIPFORGE AI - RUN SUMMARY")
    print("=" * 72)
    print(f"Mode:            {'Interactive' if interactive else 'Silent'}")
    if platform == "youtube":
        print(f"Platform:        YouTube Shorts")
    else:
        print(f"Platform:        {platform.title()}")
    print(f"Canvas:          {ratio} ({out_w}x{out_h}) | Resize: {mode}")
    print(f"Clip Mode:       {clip_mode_label}")
    print(f"Meta style:      {final_meta_style}")
    print(f"Filters:         {'OFF' if (not filters_enabled or filter_preset == 'None (No Filter)') else filter_preset}")
    print(f"FFmpeg quality:  {output_quality}")
    print(f"Plan:            {plan} | AI enabled: {ai_enabled} (meta only)")
    print(f"Input videos:    {len(input_videos)}")
    print(f"Captions:        {'ON' if captions_enabled else 'OFF'} (auto EN/Roman)")
    print("=" * 72)

    if not args.yes:
        if not ask_yes_no("Proceed?", default_yes=True):
            print("[CANCELLED] Cancelled.")
            return

    # ============================================================
    # Processing loop
    # ============================================================
    for input_video in input_videos:
        print("\n" + "-" * 72)
        print("Processing:", input_video.name)
        print("-" * 72)
        from src.pipeline.cut_shorts import safe_slug, cut_all  # project short rendering stage

        tag = safe_slug(input_video.stem)

        # Ã°Å¸â€Â¥ GUI / CLI override: custom output base folder
        if getattr(args, "out_dir_base", None):
            base_out = Path(args.out_dir_base)
            captions_dir = base_out / "captions"
            reports_dir = base_out / "reports"

            captions_dir.mkdir(parents=True, exist_ok=True)
            reports_dir.mkdir(parents=True, exist_ok=True)
            out_shorts_dir = base_out / "shorts" / tag
        else:
            out_shorts_dir = p("data", "output", "shorts", tag)
            captions_dir = p("data", "output", "captions")
            reports_dir = p("data", "output", "reports")
            captions_dir.mkdir(parents=True, exist_ok=True)
            reports_dir.mkdir(parents=True, exist_ok=True)

        audio_wav = p("data", "work", "audio", input_video.stem + ".wav")
        transcript_json = p("data", "work", "transcripts", input_video.stem + ".json")
        transcript_json_en_meta = p("data", "work", "transcripts", input_video.stem + ".en.meta.json")
        segments_json = p("data", "work", "segments", input_video.stem + "_segments.json")

        # 1) Audio
        set_progress(2, "Extracting Audio")
        print("[stage] Audio extracting...", flush=True)
        try:
            extract(input_video, audio_wav, ffmpeg_path=ffmpeg_path)
        except TypeError:
            extract(input_video, audio_wav)

        whisper_mod = __import__("src.pipeline.transcribe_whisper", fromlist=["transcribe"])

        # 2) Whisper transcribe (SOURCE) Ã¢â‚¬â€ timings + words
        print(f"[stage] Whisper transcribing (model={model_name})...")
        whisper_source = _transcribe_with_cache(
            whisper_mod,
            input_video=input_video,
            audio_wav=audio_wav,
            out_json=transcript_json,
            model_name=model_name,
            task="transcribe",
            settings=settings,
        )

        detected_lang = _norm_lang(whisper_source.get("language", "") or "") or "unknown"
        set_progress(2, f"Audio Transcribed ({detected_lang})")
        print(f"[stage] Language detected: {detected_lang}", flush=True)

        # 3) META + selection tracks.
        base_lang = detected_lang
        configured_meta_style = final_meta_style
        run_meta_style = "roman" if configured_meta_style == "auto" and base_lang in ("ur", "hi", "pa", "punjabi") else ("en" if configured_meta_style == "auto" else configured_meta_style)
        settings["meta_output_style"] = run_meta_style
        print(f"[Meta] output style selected: {run_meta_style} (policy={configured_meta_style}, lang={base_lang})", flush=True)
        captions_roman_flag = bool(settings.get("captions_roman_enabled", False))

        if base_lang in ("ur", "hi", "pa", "punjabi"):
            translate_enabled = bool(settings.get("captions_translate_whisper", True))
            if translate_enabled:
                print("[stage] Translating source transcript for metadata/selection...", flush=True)
                whisper_result_for_meta = _transcribe_with_cache(
                    whisper_mod,
                    input_video=input_video,
                    audio_wav=audio_wav,
                    out_json=transcript_json_en_meta,
                    model_name=model_name,
                    task="translate",
                    settings=settings,
                )
            else:
                whisper_result_for_meta = whisper_source
        else:
            print("[Meta] using source track directly (no translate needed).", flush=True)
            whisper_result_for_meta = whisper_source

        selection_transcript = _build_selection_transcript(
            source_result=whisper_source,
            meta_result=whisper_result_for_meta,
            detected_lang=base_lang,
            settings=settings,
        )

        inferred_category, category_info = infer_music_category(
            selection_transcript,
            editing_style=str(settings.get("editing_style_selected", "") or ""),
            platform=platform,
            fallback="cinematic",
        )
        settings["content_category"] = inferred_category
        settings["content_category_info"] = category_info
        print(f"[Meta] content category inferred: {inferred_category} | {', '.join(category_info.get('reasons', []) or ['transcript/style signal'])}", flush=True)

        # 4) Segment selection.
        set_progress(3, "Detecting Highlights")
        print("[stage] Highlights selecting segments...", flush=True)
        video_duration = _ffprobe_duration_seconds(ffprobe_path, input_video)
        if clip_mode == "manual":
            segments = _segments_from_manual(
                video_duration=video_duration,
                max_shorts=max_shorts,
                ranges_str=getattr(args, "manual_ranges", None),
            )
        elif clip_mode == "simple_auto":
            segments = _segments_from_simple_auto(
                whisper_result=selection_transcript,
                video_duration=video_duration,
                min_len=min_len,
                max_len=max_len,
                max_shorts=max_shorts,
                detected_lang=base_lang,
                settings=settings,
                simple_auto_mode=getattr(args, "simple_auto_mode", None),
                simple_auto_chunk_len=getattr(args, "simple_auto_chunk_len", None),
                simple_auto_gap_thr=getattr(args, "simple_auto_gap_thr", None),
                interactive=interactive,
            )
        else:
            if base_lang not in ("en", "unknown") and not _semantic_allowed_for_lang(base_lang, settings):
                fallback_mode = _fallback_clip_mode_for_non_english(settings)
                print(f"[Selection] Semantic disabled for {base_lang}; using {fallback_mode}.", flush=True)
                if fallback_mode == "manual":
                    segments = _segments_from_manual(
                        video_duration=video_duration,
                        max_shorts=max_shorts,
                        ranges_str=getattr(args, "manual_ranges", None),
                    )
                else:
                    segments = _segments_from_simple_auto(
                        whisper_result=selection_transcript,
                        video_duration=video_duration,
                        min_len=min_len,
                        max_len=max_len,
                        max_shorts=max_shorts,
                        detected_lang=base_lang,
                        settings=settings,
                        simple_auto_mode=getattr(args, "simple_auto_mode", "silence"),
                        simple_auto_chunk_len=getattr(args, "simple_auto_chunk_len", None),
                        simple_auto_gap_thr=getattr(args, "simple_auto_gap_thr", None),
                        interactive=False,
                    )
            else:
                keywords = load_keywords(p("config", "keywords.txt"))
                segments = pick_segments(
                    selection_transcript,
                    keywords,
                    min_len=min_len,
                    max_len=max_len,
                    max_shorts=max_shorts,
                )
                if not segments:
                    segments = _segments_from_simple_auto(
                        whisper_result=selection_transcript,
                        video_duration=video_duration,
                        min_len=min_len,
                        max_len=max_len,
                        max_shorts=max_shorts,
                        detected_lang=base_lang,
                        settings=settings,
                        simple_auto_mode="silence",
                        interactive=False,
                    )

        save_segments(segments, segments_json)
        print(f"[stage] Segments selected: {len(segments)} (mode={clip_mode})", flush=True)

        # Captions must stay on the original source timing/text. For Urdu/Hindi/Punjabi
        # Roman captions are generated from the source track, not from translated meta text.
        if base_lang in ("ur", "hi", "pa", "punjabi") and captions_roman_flag:
            whisper_for_captions = whisper_source
            final_captions_style = "roman"
        else:
            whisper_for_captions = whisper_source
            final_captions_style = "source"
        # 7) Cut shorts + captions
        set_progress(4, "Rendering Shorts")
        print("[stage] Cutting shorts + captions...", flush=True)

        short_files = cut_all(
            input_video=input_video,

            # WHISPER TRACKS
            whisper_source_result=whisper_source,            # original language + timings
            whisper_meta_result=whisper_result_for_meta,     # EN or source (META base)
            whisper_captions_result=whisper_for_captions,    # Ã¢Å“â€¦ plan/lang based captions track

            segments=segments,
            out_dir=out_shorts_dir,
            out_w=out_w,
            out_h=out_h,
            mode=mode,
            platform=platform,
            keywords_path=p("config", "keywords.txt"),
            look=settings.get("look_presets"),

            # REFRAME / FILTER
            reframe_enabled=reframe_enabled,
            reframe_kind=reframe_kind,
            reframe_cfg=reframe_cfg,
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_path,
            filter_preset=(filter_preset if filters_enabled else "None (No Filter)"),
            quality=output_quality,
            encode_cfg=encode_cfg,

            # Ã°Å¸â€Â  CAPTIONS SETTINGS (auto EN/Roman)
            captions_enabled=captions_enabled,
            captions_dir=captions_dir,
            caption_start_bias_sec=caption_start_bias_sec,
            caption_uppercase=caption_uppercase,
            caption_text_case=caption_text_case,
            caption_italic=caption_italic,
            captions_strict_timing=captions_strict_timing,

            burn_debug=bool(args.burn_debug),
            settings=settings,
        )

        set_progress(7, "Writing Metadata")
        print("[stage] Shorts created:", len(short_files), flush=True)

        captions_track_kind = final_captions_style
        effective_clip_mode = clip_mode

        # 8) Report
        report_path = reports_dir / f"{input_video.stem}_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "input_video": str(input_video),
            "mode": ("interactive" if interactive else "silent"),
            "plan": plan,
            "ai_enabled": ai_enabled,

            # captions side
            "ai_translate_captions_openai": False,
            "captions_translate_whisper": bool(captions_translate_whisper),
            "captions_track_kind": captions_track_kind,

            "ai_enhance_meta": (bool(ai_cfg.get("enhance_meta", False)) if plan == "paid" else False),
            "run_mode": settings.get("run_mode", None),
            "output_quality": output_quality,
            "output_resolution": str(getattr(args, "output_resolution", "1080p") or "1080p"),
            "platform": platform,
            "clip_mode_requested": clip_mode,
            "clip_mode_used": effective_clip_mode,
            "aspect_ratio": ratio,
            "output_size": f"{out_w}x{out_h}",
            "resize_mode": mode,

            "captions_enabled": bool(captions_enabled),
            "caption_case": caption_text_case,
            "caption_uppercase": bool(caption_uppercase),
            "caption_italic": bool(caption_italic),

            "reframe_enabled": reframe_enabled,
            "reframe_kind": reframe_kind,
            "whisper_model": model_name,
            "detected_language": detected_lang,
            "filters_enabled": filters_enabled,
            "filter_preset": filter_preset,
            "ffmpeg_path": ffmpeg_path,
            "ffprobe_path": ffprobe_path,
            "segments_json": str(segments_json),
            "shorts": [str(x) for x in short_files],
            "burn_debug": bool(args.burn_debug),

            # yahan ab wahi style jo upar decide hua:
            "final_captions_style": final_captions_style,
            "final_meta_style": settings.get("meta_output_style", final_meta_style),
        }

        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        set_progress(8, "Building ZIP Package")
        print("[stage] Report saved:", report_path, flush=True)

    set_progress(8, "Building ZIP Package")
    print("\n[stage] DONE", flush=True)


if __name__ == "__main__":
    main()








