from pathlib import Path  # provides object-oriented file paths
def srt_time(sec: float) -> str:# handles srt time behavior
    if sec < 0: sec = 0
    ms = int(round(sec * 1000))
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
def write_srt_for_clip(whisper_result: dict, clip_start: float, clip_end: float, out_srt: Path) -> None:  # writes generated data to disk
    segs = whisper_result.get("segments", [])
    lines = []
    idx = 1

    for seg in segs:
        s = float(seg["start"])
        e = float(seg["end"])
        if e <= clip_start:
            continue
        if s >= clip_end:
            break

        # overlap portion
        os = max(s, clip_start) - clip_start
        oe = min(e, clip_end) - clip_start
        text = (seg.get("text") or "").strip()
        if not text:
            continue

        lines.append(str(idx))
        lines.append(f"{srt_time(os)} --> {srt_time(oe)}")
        lines.append(text)
        lines.append("")
        idx += 1

    out_srt.parent.mkdir(parents=True, exist_ok=True)
    out_srt.write_text("\n".join(lines), encoding="utf-8")
