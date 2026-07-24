from __future__ import annotations  # enables future Python language features
from pathlib import Path  # provides object-oriented file paths
from typing import List, Tuple, Dict, Any  # adds type hint helpers
import re  # matches and cleans text with regular expressions


# ============================================================
# Basic helpers
# ============================================================
def sec_to_ass_time(t: float) -> str:# handles sec to ass time behavior
    """Convert seconds -> ASS time (H:MM:SS.cc)."""
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))  # centiseconds
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
def sanitize_ass_text(s: str) -> str:# sanitizes ass text so it is safe to use
    """Escape ASS special braces."""
    s = s.replace("{", r"\{").replace("}", r"\}")
    return s


# ============================================================
# Whisper â†’ caption lines
# ============================================================
def build_caption_lines_from_whisper(  # constructs a command, payload, prompt, caption, or response object
    whisper_result: Dict[str, Any],
    clip_start: float,
    clip_end: float,
    *,
    bias_sec: float = 0.0,
    uppercase: bool = False,
    text_case: str = "normal",
) -> List[Tuple[str, float, float]]:
    """
    Convert whisper result into simple caption lines
    for a specific clip range [clip_start, clip_end].

    Returns list of:
        (text, start_rel, end_rel)
    where start_rel / end_rel are seconds relative to clip start.
    """
    segments = whisper_result.get("segments") or []
    out: List[Tuple[str, float, float]] = []

    if clip_end <= clip_start:
        return out

    for seg in segments:
        try:
            s_start = float(seg.get("start", 0.0) or 0.0)
            s_end = float(seg.get("end", 0.0) or 0.0)
        except Exception:
            continue

        # no overlap with this clip
        if s_end <= clip_start:
            continue
        if s_start >= clip_end:
            break

        text = (seg.get("text") or "").strip()
        if not text:
            continue

        # Clean whitespace
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue

        resolved_case = (text_case or "normal").strip().lower()
        if uppercase or resolved_case == "uppercase":
            text = text.upper()
        elif resolved_case == "lowercase":
            text = text.lower()

        # Clip to requested window
        start_clipped = max(s_start, clip_start)
        end_clipped = min(s_end, clip_end)
        if end_clipped <= start_clipped:
            continue

        # Relative to clip start
        start_rel = start_clipped - clip_start
        end_rel = end_clipped - clip_start

        # Bias agar chaho to use kar sakte ho (settings se),
        # warna default 0.0 rakha hai taake speech ke sath hi aaye.
        if bias_sec:
            start_rel = max(0.0, start_rel - bias_sec)

        out.append((text, start_rel, end_rel))

    return out
def apply_viral_word_style(text: str, letter_spacing: int = 8) -> str:  # applies the selected preset/style/value
    """
    Simple viral caption styling:
    - Some words become cyan/yellow
    - Some become bigger
    - Some become italic/bold
    """

    text = text.upper()
    words = text.split()
    if not words:
        return text

    styled_words = []

    for idx, word in enumerate(words):
        clean = re.sub(r"[^A-Za-z0-9]", "", word).lower()

        is_strong_word = len(clean) >= 4
        is_target = is_strong_word and idx % 3 == 0

        if is_target:
            # ASS color codes are BGR:
            # cyan = &H00FFFF00, soft yellow = &H0000EFFF
            color = "&H0000FFFF"   # Yellow

            styled = (
                f"{{\\fsp{letter_spacing}\\b1\\fs+8\\c{color}}}"
                f"{word}"
                f"{{\\rMain\\fsp{letter_spacing}}}"
            )
        else:
            styled = f"{{\\fsp{letter_spacing}}}{word}"

        styled_words.append(styled)

    return " ".join(styled_words)


# ============================================================
# ASS builder (simple line-by-line captions)
# ============================================================
def build_ass_from_lines(  # constructs a command, payload, prompt, caption, or response object
    lines: List[Tuple[str, float, float]],
    *,
    play_res_x: int = 1080,
    play_res_y: int = 1920,
    font_name: str = "Montserrat",
    font_size: int = 41,
    margin_l: int = 90,
    margin_v: int = 180,
    outline: int = 3,
    italic: bool = False,
    letter_spacing: int = 12,
    max_chars_per_line: int = 0,
    strict_timing: bool = False,
    primary_color: str = "&H00FFFFFF",
    outline_color: str = "&H00000000",
    back_color: str = "&H64000000",
    bold: int = 0,
    shadow: int = 0,
    alignment: int = 2,
    word_dynamic: bool = False,
    accent_color: str = "",
    accent_mode: str = "none",
    glow_color: str = "",
    glow_blur: int = 0,
) -> str:

    """
    Build a simple ASS subtitle file contents from caption lines.

    lines: list of (text, start_sec_rel, end_sec_rel)

    Behaviour:
      - Ek waqt pe sirf 1 caption block (no overlapping)
      - Har block max 2 visual lines (ASS newline se 2 lines)
      - Har block same vertical position (bottom-center)
      - Thora bada font + letter spacing
    """

    # --- normalize + sort by time ---
    norm_lines: List[Tuple[str, float, float]] = []
    for text, start_rel, end_rel in lines:
        try:
            s = float(start_rel)
            e = float(end_rel)
        except Exception:
            continue
        if e <= s:
            continue
        t = (text or "").strip()
        if not t:
            continue
        norm_lines.append((t, s, e))

    if not norm_lines:
        return ""

    norm_lines.sort(key=lambda x: x[1])  # sort by start

    # Adaptive wrapping: bigger captions get fewer words per line so text
    # stays inside the 9:16 frame; smaller captions can carry more words.
    safe_width = max(360, int(play_res_x) - (int(margin_l) * 2))
    avg_char_px = max(12.0, (float(font_size) * 0.54) + (float(letter_spacing) * 0.32))
    adaptive_chars = int(safe_width / avg_char_px)
    if max_chars_per_line and max_chars_per_line > 0:
        max_chars_per_line = min(int(max_chars_per_line), adaptive_chars)
    else:
        max_chars_per_line = adaptive_chars
    max_chars_per_line = max(10, min(34, int(max_chars_per_line)))

    # --- helper: split text into chunks with max 2 lines each ---
    def _split_text_for_two_line_chunks(txt: str) -> List[str]:# handles split text for two line chunks behavior
        """
        txt ko word-wrap karega:
        - pehle logical lines banayega max_chars_per_line per line
        - phir un lines ko 2-2 ka group bana ke '\\N' se join karega
        Har chunk = max 2 lines â†’ max 2 visual lines.
        """
        newline = r"\N"   # ASS newline token (Python raw string)
        words = txt.split()
        if not words:
            return []

        # step 1: word-wrap into single lines
        logical_lines: List[str] = []
        cur = ""
        for w in words:
            if not cur:
                cur = w
                continue

            if len(cur) + 1 + len(w) <= max_chars_per_line:
                cur = cur + " " + w
            else:
                logical_lines.append(cur)
                cur = w

        if cur:
            logical_lines.append(cur)

        # step 2: group into 2-line chunks
        chunks: List[str] = []
        for i in range(0, len(logical_lines), 2):
            group = logical_lines[i:i+2]
            chunks.append(newline.join(group))

        return chunks

    # --- HEADER / STYLE BLOCK ---
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {play_res_x}\n"
        f"PlayResY: {play_res_y}\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Main,{font_name},{font_size},"
        #  Primary       Secondary     Outline       Back
        f"{primary_color},&H000000FF,{outline_color},{back_color},"
        #   Bold  Italic  Under  Strike  ScaleX ScaleY Spacing Angle
        f"{bold},{1 if italic else 0},0,0,100,100,{letter_spacing},0,"
        # BorderStyle, Outline, Shadow,
        f"1,{outline},{shadow},"
        # Alignment(2=bottom-center),  MarginL, MgnR, MgnV, Encoding
        f"{alignment},{margin_l},0,{margin_v},1\n"
        f"Style: Glow,{font_name},{font_size},"
        f"{(glow_color or accent_color or primary_color)},&H000000FF,{(glow_color or accent_color or primary_color)},{back_color},"
        f"{bold},{1 if italic else 0},0,0,100,100,{letter_spacing},0,"
        f"1,{max(outline + 2, 5)},0,"
        f"{alignment},{margin_l},0,{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events: List[str] = []

    # --- pehle logical lines ko chunks (max 2 lines) mein split karo ---
    split_segments: List[Tuple[str, float, float]] = []
    for text, s, e in norm_lines:
        duration = e - s
        if duration <= 0:
            continue

        chunks = _split_text_for_two_line_chunks(text)
        if not chunks:
            continue

        if len(chunks) == 1:
            # single chunk â†’ full duration
            split_segments.append((chunks[0], s, e))
        else:
            # multiple chunks â†’ duration equal parts
            chunk_dur = duration / len(chunks)
            for idx, ch in enumerate(chunks):
                cs = s + idx * chunk_dur
                ce = s + (idx + 1) * chunk_dur
                split_segments.append((ch, cs, ce))

    if not split_segments:
        return header  # no events

    split_segments.sort(key=lambda x: x[1])

    MIN_DUR = 0.25  # minimum line duration (sec)
    def _apply_glow_style_text(txt: str) -> str:  # applies the selected preset/style/value
        clean = sanitize_ass_text(txt)
        if not int(glow_blur or 0):
            return ""
        return f"{{\\blur{int(glow_blur)}\\alpha&H45&\\fsp{letter_spacing}}}{clean}"
    def _apply_caption_style_text(txt: str) -> str:  # applies the selected preset/style/value
        clean = sanitize_ass_text(txt)
        mode = (accent_mode or "none").strip().lower()
        color = (accent_color or "").strip()

        if word_dynamic:
            return apply_viral_word_style(clean, letter_spacing)

        if color and mode in {"last_line", "second_line"}:
            if r"\N" in clean:
                parts = clean.split(r"\N")
                parts[-1] = f"{{\\c{color}}}{parts[-1]}{{\\c{primary_color}}}"
                clean = r"\N".join(parts)
            else:
                words = clean.split()
                if len(words) > 1:
                    split_at = max(1, len(words) // 2)
                    first = " ".join(words[:split_at])
                    second = " ".join(words[split_at:])
                    clean = f"{first} {{\\c{color}}}{second}{{\\c{primary_color}}}"
                else:
                    clean = f"{{\\c{color}}}{clean}{{\\c{primary_color}}}"

        return f"{{\\fsp{letter_spacing}}}{clean}"

    if strict_timing:
        # STRICT: Whisper ke start/end ko respect karo
        for text, start_rel, end_rel in split_segments:
            start_adj = max(0.0, float(start_rel))
            end_adj = max(float(end_rel), start_adj + MIN_DUR)
            if end_adj <= start_adj:
                continue

            txt = _apply_caption_style_text(text)
            glow_txt = _apply_glow_style_text(text)

            txt = f"{{\\fad(150,150)}}{txt}"
            if glow_txt:
                glow_txt = f"{{\\fad(150,150)}}{glow_txt}"

            start_s = sec_to_ass_time(start_adj)
            end_s = sec_to_ass_time(end_adj)

            if glow_txt:
                events.append(
                    "Dialogue: 0,"
                    f"{start_s},"
                    f"{end_s},"
                    "Glow,,0,0,0,,"
                    f"{glow_txt}"
                )

            ev = (
                "Dialogue: 1,"
                f"{start_s},"
                f"{end_s},"
                "Main,,0,0,0,,"
                f"{txt}"
            )
            events.append(ev)
    else:
        # OLD behavior: ek waqt pe sirf 1 block
        prev_end = 0.0
        for text, start_rel, end_rel in split_segments:
            start_adj = max(float(start_rel), prev_end)
            end_adj = max(float(end_rel), start_adj + MIN_DUR)
            if end_adj <= start_adj:
                continue

            txt = _apply_caption_style_text(text)
            glow_txt = _apply_glow_style_text(text)

            start_s = sec_to_ass_time(start_adj)
            end_s = sec_to_ass_time(end_adj)

            if glow_txt:
                events.append(
                    "Dialogue: 0,"
                    f"{start_s},"
                    f"{end_s},"
                    "Glow,,0,0,0,,"
                    f"{glow_txt}"
                )

            ev = (
                "Dialogue: 1,"
                f"{start_s},"
                f"{end_s},"
                "Main,,0,0,0,,"
                f"{txt}"
            )
            events.append(ev)

            prev_end = end_adj  # next line yahan se baad mein shuru hogi

    return header + "\n".join(events) + ("\n" if events else "")
def write_ass_file(content: str, out_path: Path) -> None:  # writes generated data to disk
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
