from __future__ import annotations  # enables future Python language features
import subprocess  # runs external system commands
import json  # handles JSON encode and decode
from pathlib import Path  # provides object-oriented file paths
from typing import List, Tuple, Optional, Callable  # adds type hint helpers
import cv2  # provides OpenCV image/video processing


# -----------------------------
# FF helpers
# -----------------------------
def _run_cmd(args: List[str]) -> str:  # executes a pipeline step, command, or test
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "Command failed")
    return proc.stdout
def ffprobe_json(ffprobe_path: str, video: Path) -> dict:# reads video metadata with FFprobe
    args = [
        ffprobe_path, "-v", "error",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(video),
    ]
    out = _run_cmd(args)
    return json.loads(out)
def get_video_meta(ffprobe_path: str, video: Path) -> Tuple[float, int, int, float]:  # returns a resolved value used by later code
    info = ffprobe_json(ffprobe_path, video)
    duration = float(info["format"]["duration"])
    vstream = next((s for s in info["streams"] if s.get("codec_type") == "video"), None)
    if not vstream:
        raise RuntimeError("No video stream found")

    w = int(vstream["width"])
    h = int(vstream["height"])

    fr = vstream.get("avg_frame_rate", "0/0")
    num, den = fr.split("/")
    fps = (float(num) / float(den)) if float(den) != 0 else 30.0
    if fps <= 0:
        fps = 30.0

    return duration, w, h, fps


# -----------------------------
# Crop math
# -----------------------------
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


# -----------------------------
# OpenCV detectors
# -----------------------------
# FRONTAL = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
# PROFILE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
# UPPER = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_upperbody.xml")
def _safe_load_cascade(name: str):  # sanitizes the value before it is used in paths/API output
    path = cv2.data.haarcascades + name
    c = cv2.CascadeClassifier(path)
    if c.empty():
        return None
    return c

FRONTAL = _safe_load_cascade("haarcascade_frontalface_default.xml")

# ❌ profile face hata diya
PROFILE = None

UPPER = _safe_load_cascade("haarcascade_upperbody.xml")
def detect_all_faces(  # finds highlights, faces, language, timing, or visual signals
    frame_bgr,
    *,
    enhance_low_light: bool = True,
    min_face: int = 60,
    min_upperbody: int = 120,
) -> List[Tuple[float, float, float]]:
    """
    Returns list of (cx, cy, area)
    """
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    if enhance_low_light:
        gray = cv2.equalizeHist(gray)

    faces = []
    def collect(rects, weight=1.0, flip=False):# collects collect data into one list
        if rects is None:
            return
        for x, y, w, h in rects:
            if flip:
                x = gray.shape[1] - (x + w)
            cx = x + w / 2.0
            cy = y + h / 2.0
            faces.append((cx, cy, float(w * h) * weight))

    # collect(FRONTAL.detectMultiScale(gray, 1.1, 5, minSize=(min_face, min_face)), 1.0)
    # collect(PROFILE.detectMultiScale(gray, 1.1, 4, minSize=(min_face, min_face)), 0.95)
    # collect(PROFILE.detectMultiScale(cv2.flip(gray, 1), 1.1, 4, minSize=(min_face, min_face)), 0.95, flip=True)
    # collect(UPPER.detectMultiScale(gray, 1.1, 3, minSize=(min_upperbody, min_upperbody)), 0.7)

        faces = []

    if FRONTAL is not None:
        collect(
            FRONTAL.detectMultiScale(gray, 1.1, 5, minSize=(min_face, min_face)),
            1.0
        )

    if UPPER is not None:
        collect(
            UPPER.detectMultiScale(gray, 1.1, 3, minSize=(min_upperbody, min_upperbody)),
            0.7
        )

    return faces





# -----------------------------
# Speaker lock logic
# -----------------------------
def pick_active_speaker(  # chooses a matching preset, track, or fallback
    faces: List[Tuple[float, float, float]],
    active: Optional[Tuple[float, float, float]],
    *,
    lock_radius: int = 80,
    switch_ratio: float = 1.8,
) -> Tuple[Optional[Tuple[float, float, float]], bool]:
    """
    Returns (chosen_face, switched)
    """
    if not faces:
        return active, False

    faces = sorted(faces, key=lambda f: f[2], reverse=True)
    top = faces[0]

    if active is None:
        return top, True

    ax, ay, aarea = active

    # still same speaker?
    for fx, fy, farea in faces:
        if abs(fx - ax) < lock_radius and abs(fy - ay) < lock_radius:
            return (fx, fy, farea), False

    # allow switch only if clearly dominant
    if top[2] > aarea * switch_ratio:
        return top, True

    return active, False


# -----------------------------
# Audio helpers
# -----------------------------
def extract_audio_segment(ffmpeg_path: str, inp: Path, out_audio: Path, start: float, length: float) -> None:  # pulls audio, text, frames, or metadata from source media
    _run_cmd([
        ffmpeg_path, "-y",
        "-ss", f"{start:.3f}",
        "-i", str(inp),
        "-t", f"{length:.3f}",
        "-vn",
        "-c:a", "aac", "-b:a", "128k",
        str(out_audio)
    ])
def mux_video_audio(ffmpeg_path: str, video_in: Path, audio_in: Path, out_final: Path) -> None:# combines video and audio streams into one output file
    _run_cmd([
        ffmpeg_path, "-y",
        "-i", str(video_in),
        "-i", str(audio_in),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        str(out_final)
    ])


# -----------------------------
# PUBLIC API
# -----------------------------
def reframe_face_center_clip(  # keeps the subject centered inside the output crop
    *,
    ffmpeg: str,
    ffprobe: str,
    inp_clip: Path,
    out_clip: Path,
    target_w: int = 1080,
    target_h: int = 1920,

    detect_every_n_frames: int = 6,
    smooth_alpha: float = 0.10,
    max_pan_px_per_frame: float = 10.0,

    dead_zone_px: int = 40,
    lock_strength_x: float = 0.20,

    log: Optional[Callable[[str], None]] = None,
) -> Path:
    def _log(s: str):# prints or stores a debug log message
        if log:
            log(s)

    duration, src_w, src_h, fps = get_video_meta(ffprobe, inp_clip)
    cw, ch = compute_crop_size(src_w, src_h, target_w / target_h)

    cap = cv2.VideoCapture(str(inp_clip))
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_clip.with_suffix(".__tmp.mp4")), fourcc, fps, (target_w, target_h))

    cx_s, cy_s = src_w / 2.0, src_h / 2.0
    cx_t, cy_t = cx_s, cy_s

    active_face = None
    hold_frames = int(1.5 * fps)
    hold = 0

    for i in range(int(duration * fps)):
        ok, frame = cap.read()
        if not ok:
            break

        if i % detect_every_n_frames == 0:
            faces = detect_all_faces(frame)
            new_face, switched = pick_active_speaker(faces, active_face)

            if new_face:
                if switched or hold <= 0:
                    active_face = new_face
                    hold = hold_frames
                else:
                    hold -= 1

            if active_face:
                dx = abs(active_face[0] - cx_t)
                dy = abs(active_face[1] - cy_t)
                if dx > dead_zone_px or dy > dead_zone_px:
                    cx_t, cy_t = active_face[0], active_face[1]

            cx_t = (1 - lock_strength_x) * cx_s + lock_strength_x * cx_t

        cx_s += max(-max_pan_px_per_frame, min(max_pan_px_per_frame, (cx_t - cx_s) * smooth_alpha))
        cy_s += max(-max_pan_px_per_frame, min(max_pan_px_per_frame, (cy_t - cy_s) * smooth_alpha))

        xi, yi = clamp_crop_xy(cx_s - cw / 2, cy_s - ch / 2, cw, ch, src_w, src_h)
        crop = frame[yi:yi + ch, xi:xi + cw]
        writer.write(cv2.resize(crop, (target_w, target_h)))

    cap.release()
    writer.release()

    tmp_video = out_clip.with_suffix(".__tmp.mp4")
    tmp_audio = out_clip.with_suffix(".__tmp.m4a")

    _log("[i] Extracting audio...\n")
    extract_audio_segment(ffmpeg, inp_clip, tmp_audio, 0.0, duration)

    _log("[i] Mixing audio + video...\n")
    mux_video_audio(ffmpeg, tmp_video, tmp_audio, out_clip)

    tmp_video.unlink(missing_ok=True)
    tmp_audio.unlink(missing_ok=True)

    return out_clip
