from __future__ import annotations  # enables future Python language features
import subprocess  # runs external system commands
import json  # handles JSON encode and decode
from dataclasses import dataclass  # creates lightweight data classes
from pathlib import Path  # provides object-oriented file paths
from typing import List, Tuple, Optional, Callable, Dict, Any, Union  # adds type hint helpers
import re  # matches and cleans text with regular expressions

# OpenCV optional (only needed for reframe)
try:
    import cv2  # provides OpenCV image/video processing
except Exception:
    cv2 = None


# ============================================================
# Encode / Quality (CPU-only x264)
# ============================================================

@dataclass
class EncodeConfig:  # stores validated data and related behavior for Encode Config
    """
    CPU-only encoder settings (x264 + AAC).
    """
    preset: str = "fast"      # ultrafast/veryfast/faster/fast/medium/slow/slower/veryslow
    crf: int = 20             # lower=better quality, bigger file. Typical: 18-23
    audio_bitrate: str = "160k"
    audio_rate: Optional[str] = None  # e.g. "48000" or None
    threads: Optional[int] = None     # e.g. 0/None => ffmpeg decides
    tune: Optional[str] = None        # e.g. "film", "animation"
    profile: Optional[str] = None     # e.g. "high"
    level: Optional[str] = None       # e.g. "4.1"

    @staticmethod
    def from_quality(quality: str) -> "EncodeConfig":# handles from quality behavior
        q = (quality or "").strip().lower()
        if q in ("fast", "f"):
            return EncodeConfig(preset="veryfast", crf=22, audio_bitrate="128k")
        if q in ("balanced", "b", "normal"):
            return EncodeConfig(preset="fast", crf=20, audio_bitrate="160k")
        if q in ("high", "hq", "best"):
            return EncodeConfig(preset="slow", crf=18, audio_bitrate="192k")
        return EncodeConfig(preset="fast", crf=20, audio_bitrate="160k")


EncodeCfgLike = Union[EncodeConfig, Dict[str, Any]]


# ============================================================
# FFmpeg filter escaping (CRITICAL FIX ✅)
# ============================================================
def _ffmpeg_filter_escape_value(path: Path) -> str:# handles ffmpeg filter escape value behavior
    """
    Escape a Windows path for FFmpeg filter values.
    Output example:
      C\\:/project/data/output/captions/short_01.ass

    - Convert backslashes to forward slashes
    - Escape drive-letter colon only: C:/ -> C\\:/
    - Escape apostrophes for filter quoting
    """
    s = str(Path(path).resolve()).replace("\\", "/")
    s = re.sub(r"^([A-Za-z]):/", r"\1\\:/", s)  # C:/ -> C\:/ (escaped colon)
    s = s.replace("'", r"\'")                   # escape single quotes
    return s


# ============================================================
# Encode config helpers
# ============================================================
def _resolve_encode_cfg(  # converts settings/input into a concrete path or option
    encode_cfg: Optional[EncodeCfgLike],
    quality: Optional[str],
) -> EncodeConfig:
    if isinstance(encode_cfg, EncodeConfig):
        return encode_cfg

    if isinstance(encode_cfg, dict):
        base = EncodeConfig()
        for k, v in encode_cfg.items():
            if hasattr(base, k):
                setattr(base, k, v)
        return base

    if quality:
        return EncodeConfig.from_quality(quality)

    return EncodeConfig()
def _x264_args(cfg: EncodeConfig) -> List[str]:# handles x264 args behavior
    args = ["-c:v", "libx264", "-preset", str(cfg.preset), "-crf", str(int(cfg.crf))]
    if cfg.tune:
        args += ["-tune", str(cfg.tune)]
    if cfg.profile:
        args += ["-profile:v", str(cfg.profile)]
    if cfg.level:
        args += ["-level:v", str(cfg.level)]
    if cfg.threads is not None:
        args += ["-threads", str(int(cfg.threads))]
    return args
def _aac_args(cfg: EncodeConfig) -> List[str]:# handles aac args behavior
    args = ["-c:a", "aac", "-b:a", str(cfg.audio_bitrate)]
    if cfg.audio_rate:
        args += ["-ar", str(cfg.audio_rate)]
    return args


# ============================================================
# FFmpeg / FFprobe helpers
# ============================================================
def run_ffmpeg(args: List[str]) -> None:  # executes a pipeline step, command, or test
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        raise RuntimeError(err or "FFmpeg failed")
def _run_ffprobe(args: List[str]) -> dict:  # executes a pipeline step, command, or test
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        raise RuntimeError(err or "ffprobe failed")
    return json.loads(proc.stdout or "{}")
def ffprobe_wh_fps(video: Path, ffprobe_path: str = "ffprobe") -> Tuple[int, int, float]:# reads video metadata with FFprobe
    data = _run_ffprobe([
        ffprobe_path, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-of", "json",
        str(video),
    ])
    streams = data.get("streams") or []
    if not streams:
        raise RuntimeError("ffprobe: no video stream found")

    st = streams[0]
    w = int(st["width"])
    h = int(st["height"])
    num, den = (st.get("r_frame_rate", "30/1") or "30/1").split("/")
    fps = float(num) / float(den) if float(den) != 0 else 30.0
    if fps <= 0:
        fps = 30.0
    return w, h, fps
def ffprobe_duration(video: Path, ffprobe_path: str = "ffprobe") -> float:# reads video metadata with FFprobe
    data = _run_ffprobe([
        ffprobe_path, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(video),
    ])
    d = float((data.get("format") or {}).get("duration", 0.0) or 0.0)
    return max(0.0, d)


# ============================================================
# BASIC CUT (NO FACE LOGIC) + optional filter_vf
# ============================================================
def cut_clip(  # extracts a clip segment from source video
    *,
    input_video: Path,
    start_sec: float,
    duration_sec: float,
    out_mp4: Path,
    out_w: int,
    out_h: int,
    mode: str = "crop",
    look: dict | None = None,
    filter_vf: Optional[str] = None,
    ffmpeg_path: str = "ffmpeg",
    quality: Optional[str] = None,
    encode_cfg: Optional[EncodeCfgLike] = None,
) -> None:
    input_video = Path(input_video)
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)

    cfg = _resolve_encode_cfg(encode_cfg, quality)
    mode = (mode or "crop").lower()

    if mode == "crop":
        base_vf = (
            f"scale=w={out_w}:h={out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h}"
        )
    else:
        base_vf = f"scale={out_w}:{out_h}"

    look_vf = ""
    if isinstance(look, dict):
        lv = look.get("vf") if look else None
        if isinstance(lv, str) and lv.strip():
            look_vf = lv.strip()

    filt = (filter_vf or "").strip()

    vf_parts = [base_vf]
    if look_vf:
        vf_parts.append(look_vf)
    if filt:
        vf_parts.append(filt)
    vf_parts.append("format=yuv420p")
    vf = ",".join(vf_parts)

    args = [
        ffmpeg_path, "-y",
        "-ss", f"{start_sec:.3f}",
        "-i", str(input_video),
        "-t", f"{duration_sec:.3f}",
        "-vf", vf,
        *_x264_args(cfg),
        "-pix_fmt", "yuv420p",
        *_aac_args(cfg),
        "-movflags", "+faststart",
        str(out_mp4),
    ]
    run_ffmpeg(args)


# ============================================================
# ASS SUBTITLE BURN (CPU-only) ✅ FIXED
# ============================================================
def burn_ass(# burns styled subtitles into a video file
    *,
    input_video: Path,
    ass_file: Path,
    out_video: Path,
    ffmpeg_path: str = "ffmpeg",
    quality: Optional[str] = None,
    encode_cfg: Optional[EncodeCfgLike] = None,
    fonts_dir: Optional[Path] = None,
    debug: bool = False,
) -> None:
    input_video = Path(input_video)
    ass_file = Path(ass_file)
    out_video = Path(out_video)
    out_video.parent.mkdir(parents=True, exist_ok=True)

    if not ass_file.exists():
        raise FileNotFoundError(f"ASS file not found: {ass_file}")

    cfg = _resolve_encode_cfg(encode_cfg, quality)

    if fonts_dir is None:
        fonts_dir = Path("assets") / "fonts"

    ass_safe = _ffmpeg_filter_escape_value(ass_file)
    def _run_with_vf(vf: str):  # executes a pipeline step, command, or test
        if debug:
            print("\n[burn_ass] FFMPEG -vf =")
            print(vf)
        run_ffmpeg([
            ffmpeg_path, "-y",
            "-i", str(input_video),
            "-vf", vf,
            *_x264_args(cfg),
            "-pix_fmt", "yuv420p",
            *_aac_args(cfg),
            "-movflags", "+faststart",
            str(out_video),
        ])

    # Try with fontsdir first
    if fonts_dir and Path(fonts_dir).exists():
        fonts_safe = _ffmpeg_filter_escape_value(Path(fonts_dir))
        vf1 = f"subtitles='{ass_safe}':fontsdir='{fonts_safe}':charenc=UTF-8,format=yuv420p"
        try:
            _run_with_vf(vf1)
            return
        except Exception as e:
            if debug:
                print("[WARN] burn_ass fontsdir failed, retrying without fontsdir...")
                print(str(e)[:500])

    # Fallback without fontsdir (most compatible)
    vf2 = f"subtitles='{ass_safe}':charenc=UTF-8,format=yuv420p"
    _run_with_vf(vf2)


# ============================================================
# AUDIO EXTRACT (Whisper)
# ============================================================
def extract_audio(  # pulls audio, text, frames, or metadata from source media
    *,
    input_video: Path,
    out_wav: Path,
    ffmpeg_path: str = "ffmpeg",
    sample_rate: int = 16000,
) -> None:
    """
    Extract mono WAV for Whisper (default 16k).
    """
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    run_ffmpeg([
        ffmpeg_path, "-y",
        "-i", str(input_video),
        "-vn",
        "-ac", "1",
        "-ar", str(int(sample_rate)),
        "-c:a", "pcm_s16le",
        str(out_wav)
    ])


# ============================================================
# REFRAME (Talking-head) - SINGLE SOURCE OF TRUTH ✅
# ============================================================
def _load_frontal_cascade():  # loads required data/settings into memory
    if cv2 is None:
        return None
    try:
        base = getattr(cv2.data, "haarcascades", "")
        cc = cv2.CascadeClassifier(str(Path(base) / "haarcascade_frontalface_default.xml"))
        if cc is not None and not cc.empty():
            return cc
    except Exception:
        pass
    return None
def _open_video_writer_safely(# opens video writer safely safely
    out_path: Path,
    fps: float,
    size: Tuple[int, int],
):
    if cv2 is None:
        raise RuntimeError("OpenCV missing. Install: pip install opencv-python")

    w, h = size
    mp4_try = [
        ("mp4v", out_path),
        ("avc1", out_path),
        ("H264", out_path),
        ("XVID", out_path),
    ]

    for fourcc_str, path in mp4_try:
        try:
            writer = cv2.VideoWriter(
                str(path),
                cv2.VideoWriter_fourcc(*fourcc_str),
                fps,
                (w, h),
            )
            if writer.isOpened():
                return writer, path
        except Exception:
            pass

    avi_path = out_path.with_suffix(".avi")
    writer = cv2.VideoWriter(
        str(avi_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        fps,
        (w, h),
    )
    if writer.isOpened():
        return writer, avi_path

    raise RuntimeError("Failed to create VideoWriter (codec issue).")
def compute_crop_size(src_w: int, src_h: int, target_ar: float) -> Tuple[int, int]:# calculates crop size
    src_ar = src_w / src_h
    if src_ar >= target_ar:
        ch = src_h
        cw = int(round(ch * target_ar))
    else:
        cw = src_w
        ch = int(round(cw / target_ar))
    return min(cw, src_w), min(ch, src_h)
def clamp_crop_xy(x: float, y: float, cw: int, ch: int, src_w: int, src_h: int) -> Tuple[int, int]:# limits a value so it stays inside the allowed range
    xi = int(round(x))
    yi = int(round(y))
    xi = max(0, min(xi, src_w - cw))
    yi = max(0, min(yi, src_h - ch))
    return xi, yi
def reframe_talking_head(  # keeps the subject centered inside the output crop
    *,
    ffmpeg_path: str,
    ffprobe_path: str,
    inp: Path,
    out_final: Path,
    start: float,
    length: float,
    target_w: int,
    target_h: int,
    detect_every_n_frames: int = 6,
    smooth_alpha: float = 0.12,
    max_pan_px_per_frame: float = 12.0,
    enhance_low_light: bool = True,
    min_face: int = 60,
    dead_zone_px: int = 40,
    lock_strength_x: float = 0.25,
    log: Optional[Callable[[str], None]] = None,
    quality: Optional[str] = None,
    encode_cfg: Optional[EncodeCfgLike] = None,
) -> Path:
    if cv2 is None:
        raise RuntimeError("OpenCV not installed. Run: pip install opencv-python")
    def _log(msg: str):# prints or stores a debug log message
        if log:
            log(msg)

    cfg = _resolve_encode_cfg(encode_cfg, quality)

    inp = Path(inp)
    out_final = Path(out_final)
    out_final.parent.mkdir(parents=True, exist_ok=True)

    face = _load_frontal_cascade()
    if face is None:
        raise RuntimeError("Frontal face cascade not found in OpenCV installation")

    src_w, src_h, fps = ffprobe_wh_fps(inp, ffprobe_path=ffprobe_path)
    fps = float(fps or 30.0)

    target_ar = target_w / target_h
    cw, ch = compute_crop_size(src_w, src_h, target_ar)

    cap = cv2.VideoCapture(str(inp))
    if not cap.isOpened():
        raise RuntimeError("Failed to open video with OpenCV")

    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)
    total_frames = max(1, int(round(length * fps)))

    tmp_video_mp4 = out_final.parent / (out_final.stem + ".__temp_video.mp4")
    tmp_audio = out_final.parent / (out_final.stem + ".__temp_audio.m4a")

    writer, tmp_video_real = _open_video_writer_safely(tmp_video_mp4, fps, (target_w, target_h))

    cx_s = src_w / 2.0
    cy_s = src_h / 2.0
    cx_t = cx_s
    cy_t = cy_s

    last_good = (cx_s, cy_s)
    last_accept = (cx_s, cy_s)

    lock_strength_x = max(0.0, min(1.0, float(lock_strength_x)))
    dead_zone_px = max(0, int(dead_zone_px))

    for i in range(total_frames):
        ret, frame = cap.read()
        if not ret:
            break

        if i % max(1, detect_every_n_frames) == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if enhance_low_light:
                gray = cv2.equalizeHist(gray)

            faces = face.detectMultiScale(gray, 1.1, 5, minSize=(min_face, min_face))
            if faces is not None and len(faces) > 0:
                x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
                fc = (x + w / 2.0, y + h / 2.0)

                dx = abs(fc[0] - last_accept[0])
                dy = abs(fc[1] - last_accept[1])

                if dx > dead_zone_px or dy > dead_zone_px:
                    cx_t, cy_t = fc
                    last_good = (cx_t, cy_t)
                    last_accept = (cx_t, cy_t)
                else:
                    cx_t, cy_t = last_good
            else:
                cx_t, cy_t = last_good

            cx_t = (1.0 - lock_strength_x) * cx_s + lock_strength_x * cx_t

        cx_new = (1.0 - smooth_alpha) * cx_s + smooth_alpha * cx_t
        cy_new = (1.0 - smooth_alpha) * cy_s + smooth_alpha * cy_t

        dxm = max(-max_pan_px_per_frame, min(max_pan_px_per_frame, cx_new - cx_s))
        dym = max(-max_pan_px_per_frame, min(max_pan_px_per_frame, cy_new - cy_s))
        cx_s += dxm
        cy_s += dym

        x = cx_s - cw / 2.0
        y = cy_s - ch / 2.0
        xi, yi = clamp_crop_xy(x, y, cw, ch, src_w, src_h)

        cropped = frame[yi:yi + ch, xi:xi + cw]
        resized = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        writer.write(resized)

    writer.release()
    cap.release()

    _log("[i] Extracting audio...\n")
    run_ffmpeg([
        ffmpeg_path, "-y",
        "-ss", f"{start:.3f}",
        "-i", str(inp),
        "-t", f"{length:.3f}",
        "-vn",
        "-c:a", "aac", "-b:a", "128k",
        str(tmp_audio)
    ])

    _log("[i] Mixing audio + video...\n")
    run_ffmpeg([
        ffmpeg_path, "-y",
        "-i", str(tmp_video_real),
        "-i", str(tmp_audio),
        *_x264_args(cfg),
        "-pix_fmt", "yuv420p",
        *_aac_args(cfg),
        "-shortest",
        "-movflags", "+faststart",
        str(out_final)
    ])

    try:
        Path(tmp_video_real).unlink(missing_ok=True)
        tmp_audio.unlink(missing_ok=True)
        tmp_video_mp4.unlink(missing_ok=True)
    except Exception:
        pass

    return out_final
