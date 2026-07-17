from __future__ import annotations  # enables future Python language features
from pathlib import Path  # provides object-oriented file paths
import json  # handles JSON encode and decode
import re  # matches and cleans text with regular expressions
from typing import List, Tuple, Optional  # adds type hint helpers


# -------------------------
# Keyword loading
# -------------------------
def load_keywords(path: Path) -> List[Tuple[str, float]]:  # loads required data/settings into memory
    if not path.exists():
        return []

    out: List[Tuple[str, float]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        kw, wt = _parse_weighted_keyword(line)
        kw = kw.strip()
        if kw:
            out.append((kw, wt))
    return out
def _parse_weighted_keyword(line: str) -> Tuple[str, float]:  # turns raw text/API data into structured values
    default_w = 2.0
    if "|" in line:
        a, b = [x.strip() for x in line.split("|", 1)]
        return _kw_weight_from_parts(a, b, default_w)
    if "=" in line:
        a, b = [x.strip() for x in line.split("=", 1)]
        return _kw_weight_from_parts(a, b, default_w)
    return line, default_w
def _kw_weight_from_parts(a: str, b: str, default_w: float) -> Tuple[str, float]:# handles kw weight from parts behavior
    if _is_number(b):
        return a, float(b)
    if _is_number(a):
        return b, float(a)
    return (a if a else b), default_w
def _is_number(s: str) -> bool:  # checks whether the condition is true
    try:
        float(s)
        return True
    except Exception:
        return False


# -------------------------
# Scoring
# -------------------------
STOPWORDS = {
    "basically", "honestly", "literally", "seriously",
    "actually", "you know"
}
def normalize(text: str) -> str:  # standardizes values before comparison or rendering
    return re.sub(r"\s+", " ", (text or "").lower()).strip()
def score_text(text: str, keywords: List[Tuple[str, float]]) -> float:  # calculates ranking values for clips or keywords
    t = normalize(text)
    score = 0.0

    for kw, w in keywords:
        kw_n = normalize(kw)
        if not kw_n:
            continue

        cnt = t.count(kw_n)
        if cnt <= 0:
            continue

        base = float(w)

        # repetition bonus (capped)
        extra = max(0, min(cnt - 1, 2))
        rep_bonus = extra * (float(w) * 0.25)

        # stopword damping
        if kw_n in STOPWORDS:
            base *= 0.5
            rep_bonus *= 0.5

        score += base + rep_bonus

    # punctuation excitement (small)
    score += min(2, t.count("!")) * 0.4
    score += min(2, t.count("?")) * 0.25

    return float(score)


# -------------------------
# Shared helpers
# -------------------------
def _sanitize_segment(# sanitizes segment so it is safe to use
    start: float,
    end: float,
    text: str = "",
    score: float = 0.0,
    source: str = "rule",
) -> dict:
    s = float(start)
    e = float(end)
    if e < s:
        s, e = e, s
    dur = max(0.0, e - s)
    return {
        "start": s,
        "end": e,
        "duration": float(dur),
        "score": float(score),
        "text": (text or "").strip(),
        "source": (source or "rule").strip().lower(),
    }
def _overlaps(a: dict, b: dict) -> bool:# handles overlaps behavior
    return not (float(a["end"]) <= float(b["start"]) or float(b["end"]) <= float(a["start"]))
def _collect_all_word_times(whisper_result: dict) -> List[Tuple[float, float]]:# collects all word times data into one list
    out: List[Tuple[float, float]] = []
    for seg in whisper_result.get("segments", []) or []:
        for w in (seg.get("words") or []):
            ws = float(w.get("start", 0.0))
            we = float(w.get("end", 0.0))
            if we > ws:
                out.append((ws, we))
    out.sort(key=lambda x: x[0])
    return out
def _infer_audio_duration(whisper_result: dict) -> float:# infers audio duration from available data
    segs = whisper_result.get("segments", []) or []
    if not segs:
        return 0.0
    try:
        return float(segs[-1].get("end", 0.0) or 0.0)
    except Exception:
        return 0.0


# -------------------------
# A) RULE-BASED picker (your current logic, but schema-fixed)
# -------------------------
def pick_segments(  # chooses a matching preset, track, or fallback
    whisper_result: dict,
    keywords: List[Tuple[str, float]],
    min_len: int = 20,
    max_len: int = 60,
    max_shorts: int = 10,
    min_score: float = 6.0,
) -> list[dict]:
    """
    Rule-based highlights using keyword scoring.
    Returns schema-safe segments with source='rule'
    """
    segs = whisper_result.get("segments", []) or []
    if not segs:
        return []

    candidates: List[dict] = []
    n = len(segs)

    min_len = max(1, int(min_len))
    max_len = max(min_len + 1, int(max_len))
    max_shorts = max(1, int(max_shorts))
    min_score = float(min_score)

    # stride = 2 (reduce noise)
    for i in range(0, n, 2):
        start = float(segs[i].get("start", 0.0))
        text_parts: List[str] = []
        end = start

        for j in range(i, n):
            end = float(segs[j].get("end", start))
            dur = end - start
            if dur > max_len:
                break

            text_parts.append((segs[j].get("text") or "").strip())

            if dur >= min_len:
                combined = " ".join(t for t in text_parts if t).strip()
                if not combined:
                    continue

                s = float(score_text(combined, keywords))

                # early hook boost
                first_quarter = combined[: max(20, len(combined) // 4)]
                if any((kw or "").lower() in first_quarter.lower() for kw, _ in (keywords or [])):
                    s *= 1.25

                if s >= min_score:
                    candidates.append(
                        _sanitize_segment(
                            start=start,
                            end=end,
                            text=combined,
                            score=round(s, 2),
                            source="rule",
                        )
                    )

    candidates.sort(key=lambda x: float(x["score"]), reverse=True)

    picked: List[dict] = []
    for c in candidates:
        if len(picked) >= max_shorts:
            break
        if all(not _overlaps(c, p) for p in picked):
            picked.append(c)

    picked.sort(key=lambda x: float(x["start"]))
    return picked


# -------------------------
# C) SIMPLE AUTO (uniform chunks OR silence-based)
# -------------------------
def pick_segments_simple_auto(  # chooses a matching preset, track, or fallback
    whisper_result: dict,
    *,
    mode: str = "uniform",                 # "uniform" | "silence"
    min_len: int = 20,
    max_len: int = 60,
    max_shorts: int = 10,
    uniform_chunk_len: Optional[int] = None,   # if None, uses max_len
    silence_gap_sec: float = 0.45,             # gap threshold between words
) -> list[dict]:
    """
    Simple Auto:
      - uniform: cuts whole video into equal chunks
      - silence: cuts around pauses (word gaps) using whisper word timing

    Returns schema-safe segments with source='simple'
    """
    mode = (mode or "uniform").strip().lower()
    min_len = max(1, int(min_len))
    max_len = max(min_len + 1, int(max_len))
    max_shorts = max(1, int(max_shorts))

    duration = _infer_audio_duration(whisper_result)
    if duration <= 0:
        return []

    if mode == "silence":
        return _simple_auto_silence(
            whisper_result=whisper_result,
            duration=duration,
            min_len=min_len,
            max_len=max_len,
            max_shorts=max_shorts,
            gap_threshold=float(silence_gap_sec),
        )

    # default: uniform
    chunk_len = int(uniform_chunk_len) if uniform_chunk_len else int(max_len)
    chunk_len = max(min_len, min(chunk_len, max_len))

    out: List[dict] = []
    t = 0.0
    i = 0
    while t < duration and len(out) < max_shorts:
        s = float(t)
        e = float(min(duration, t + chunk_len))
        if (e - s) >= min_len:
            out.append(_sanitize_segment(s, e, text="", score=0.0, source="simple"))
        t = e
        i += 1
        if i > 10000:
            break

    return out
def _simple_auto_silence(# creates simple clip windows using silence gaps
    whisper_result: dict,
    duration: float,
    min_len: int,
    max_len: int,
    max_shorts: int,
    gap_threshold: float,
) -> list[dict]:
    """
    Silence-based:
    - Find gaps between words >= gap_threshold
    - Use those as potential cut points
    - Build segments roughly between pauses (but enforce min_len/max_len)
    """
    words = _collect_all_word_times(whisper_result)
    if not words:
        # fallback to uniform if words missing
        return pick_segments_simple_auto(
            whisper_result,
            mode="uniform",
            min_len=min_len,
            max_len=max_len,
            max_shorts=max_shorts,
            uniform_chunk_len=max_len,
        )

    # build cut points from gaps
    cut_points = [0.0]
    for i in range(1, len(words)):
        prev_end = words[i - 1][1]
        cur_start = words[i][0]
        if (cur_start - prev_end) >= gap_threshold:
            # cut in the middle of silence
            mid = (prev_end + cur_start) / 2.0
            cut_points.append(float(mid))
    cut_points.append(float(duration))

    cut_points = sorted(set(max(0.0, min(duration, x)) for x in cut_points))

    segments: List[dict] = []
    s = cut_points[0]

    for cp in cut_points[1:]:
        e = float(cp)
        if e <= s:
            continue

        # If segment too small -> keep accumulating
        if (e - s) < min_len:
            continue

        # If segment too big -> split internally by max_len
        while (e - s) > max_len and len(segments) < max_shorts:
            seg_end = s + max_len
            segments.append(_sanitize_segment(s, seg_end, text="", score=0.0, source="simple"))
            s = seg_end

        if len(segments) >= max_shorts:
            break

        # finalize this segment
        if (e - s) >= min_len and (e - s) <= max_len:
            segments.append(_sanitize_segment(s, e, text="", score=0.0, source="simple"))
            s = e

        if len(segments) >= max_shorts:
            break

    return segments


# -------------------------
# Save segments
# -------------------------
def save_segments(segments: list[dict], out_json: Path) -> None:  # saves generated state or output files
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
