from __future__ import annotations  # enables future Python language features
from pathlib import Path  # provides object-oriented file paths
import json  # handles JSON encode and decode
import math  # provides math functions and constants
import wave  # reads and writes WAV audio files
import contextlib  # provides context-manager helpers
import time  # measures time, delays, and elapsed seconds
import os  # works with environment variables and OS paths
from typing import Optional, Dict, Any, List  # adds type hint helpers
from faster_whisper import WhisperModel  # runs Faster-Whisper speech recognition
from tqdm import tqdm  # shows terminal progress bars


# -------------------------------------------------
# WHISPER MODEL CACHE
# -------------------------------------------------
# Default is auto:
#   - Try CUDA when available/requested.
#   - Fall back to stable CPU int8 if GPU is missing or fails.
_WHISPER_CACHE: Dict[tuple[str, str, str], WhisperModel] = {}
_WHISPER_RUNTIME: Dict[str, str] = {"model": "small", "device": "cpu", "compute_type": "int8"}
def _cuda_available() -> bool:# handles cuda available behavior
    try:
        import torch  # type: ignore
        return bool(torch.cuda.is_available())
    except Exception:
        pass
    try:
        import ctranslate2  # type: ignore
        return int(ctranslate2.get_cuda_device_count()) > 0
    except Exception:
        return False
def _resolve_runtime(settings: Optional[Dict[str, Any]], *, force_cpu: bool = False) -> tuple[str, str, str]:  # converts settings/input into a concrete path or option
    settings = settings or {}
    model_name = str(settings.get("whisper_model", "small") or "small").strip()
    device_setting = str(settings.get("whisper_device", "auto") or "auto").strip().lower()
    enable_gpu = settings.get("enable_gpu_acceleration", "auto")

    if force_cpu:
        return model_name, "cpu", str(settings.get("whisper_compute_type_cpu", "int8") or "int8")

    if device_setting in ("cpu", "cuda"):
        device = device_setting
    else:
        gpu_allowed = str(enable_gpu).strip().lower() not in ("false", "0", "no", "off")
        device = "cuda" if gpu_allowed and _cuda_available() else "cpu"

    if device == "cuda":
        compute_type = str(settings.get("whisper_compute_type_cuda", "float16") or "float16")
    else:
        compute_type = str(settings.get("whisper_compute_type_cpu", settings.get("whisper_compute_type", "int8")) or "int8")
    return model_name, device, compute_type
def _get_model(settings: Optional[Dict[str, Any]] = None, *, force_cpu: bool = False) -> WhisperModel:  # returns a resolved value used by later code
    global _WHISPER_RUNTIME
    model_name, device, compute_type = _resolve_runtime(settings, force_cpu=force_cpu)
    key = (model_name, device, compute_type)
    if key not in _WHISPER_CACHE:
        try:
            _WHISPER_CACHE[key] = WhisperModel(model_name, device=device, compute_type=compute_type)
            _WHISPER_RUNTIME = {"model": model_name, "device": device, "compute_type": compute_type}
            print(f"[whisper] loaded model={model_name} device={device} compute_type={compute_type}", flush=True)
        except Exception as e:
            if device != "cpu":
                print(f"[whisper] GPU unavailable/failed ({e}); falling back to CPU int8.", flush=True)
                return _get_model(settings, force_cpu=True)
            raise
    else:
        _WHISPER_RUNTIME = {"model": model_name, "device": device, "compute_type": compute_type}
    return _WHISPER_CACHE[key]
def _audio_duration_seconds(wav_path: Path) -> float:# calculates the audio duration seconds ratio
    with contextlib.closing(wave.open(str(wav_path), "rb")) as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return frames / float(rate)
def transcribe(  # converts audio into timestamped transcript text
    audio_wav: Path,
    out_json: Path,
    *,
    model_name: str = "small",   # 🔒 LOCKED — arg ignored, sirf compatibility
    task: str = "transcribe",
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """
    task:
      - "transcribe" (default)  -> keeps original language (TRUST word timestamps)
      - "translate"             -> forces English output (DO NOT TRUST word timestamps)

    Auto-device faster-whisper:

    Reads from settings.yaml (OPTIONAL):
      - whisper_batch_size
      - whisper_beam_size
      - whisper_beam_size_translate
      - whisper_initial_prompt
      - whisper_temperature
      - whisper_condition_on_previous

    Runtime:
      - whisper_device="auto" tries CUDA when available.
      - CPU fallback uses int8 for stability.

    Output schema:
      - segments[].words preserved for SOURCE
      - root-level "words" (flat list) ONLY for SOURCE
      - for task="translate": words are intentionally empty (text-only pass)
    """
    out_json = Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)

    settings = settings or {}

    # ---------------- basic settings ----------------
    batch_size = int(settings.get("whisper_batch_size", 16))

    base_beam_size = int(settings.get("whisper_beam_size", 5))
    # translate ke liye alag beam size allow karo (zyada accurate)
    beam_size_translate = int(settings.get("whisper_beam_size_translate", max(8, base_beam_size)))

    vad_filter = bool(settings.get("whisper_vad_filter", True))

    # optional tuning
    initial_prompt = str(settings.get("whisper_initial_prompt", "") or "").strip()
    # default: 0.0 → deterministic, better accuracy
    temperature = float(settings.get("whisper_temperature", 0.0))
    condition_on_previous = bool(settings.get("whisper_condition_on_previous", False))

    task = (task or "transcribe").strip().lower()
    if task not in ("transcribe", "translate"):
        task = "transcribe"

    # 🔒 RULE: Only SOURCE pass uses word timestamps
    use_word_ts = (task == "transcribe")

    # per-task beam size
    if task == "translate":
        beam_size = beam_size_translate
    else:
        beam_size = base_beam_size

    total_sec = _audio_duration_seconds(Path(audio_wav))
    total_ms = max(1, int(total_sec * 1000))

    # Auto device model, with CPU fallback if GPU is not available.
    model = _get_model(settings)
    locked_model_name = _WHISPER_RUNTIME.get("model", "small")
    locked_device = _WHISPER_RUNTIME.get("device", "cpu")
    locked_compute_type = _WHISPER_RUNTIME.get("compute_type", "int8")

    segments_out: List[dict] = []
    full_text_parts: List[str] = []
    flat_words: List[dict] = []  # SOURCE only

    pbar = tqdm(
        total=100,
        desc=("Transcribing" if task == "transcribe" else "Translating"),
        ncols=80,
    )
    last_percent = 0
    last_report_percent = -1
    progress_started_at = time.time()
    def _emit_terminal_progress(percent_value: float):# emits terminal progress to the caller/UI
        elapsed = max(0.0, time.time() - progress_started_at)
        if percent_value > 0:
            eta = max(0.0, (elapsed / (percent_value / 100.0)) - elapsed)
            eta_text = f"eta={eta:.1f}s"
        else:
            eta_text = "eta=--"
        label = "Transcribing" if task == "transcribe" else "Translating"
        print(f"{label}: {percent_value:.2f}/100.00 elapsed={elapsed:.1f}s {eta_text}", flush=True)

    _emit_terminal_progress(0.0)
    def _do_transcribe(with_batch: bool):# handles do transcribe behavior
        kwargs: Dict[str, Any] = dict(
            beam_size=beam_size,
            vad_filter=vad_filter,
            word_timestamps=use_word_ts,  # ✅ SOURCE only
            task=task,
            temperature=temperature,
            condition_on_previous_text=condition_on_previous,
        )
        # optional domain prompt (names/terms accuracy better)
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt

        if with_batch:
            kwargs["batch_size"] = batch_size

        return model.transcribe(str(audio_wav), **kwargs)

    try:
        seg_iter, info = _do_transcribe(with_batch=True)
        batch_used = batch_size
    except TypeError:
        # older faster-whisper version without batch_size kwarg
        seg_iter, info = _do_transcribe(with_batch=False)
        batch_used = None
    except Exception as e:
        if _WHISPER_RUNTIME.get("device") != "cpu":
            print(f"[whisper] GPU transcribe failed ({e}); retrying on CPU int8.", flush=True)
            model = _get_model(settings, force_cpu=True)
            locked_model_name = _WHISPER_RUNTIME.get("model", "small")
            locked_device = _WHISPER_RUNTIME.get("device", "cpu")
            locked_compute_type = _WHISPER_RUNTIME.get("compute_type", "int8")
            try:
                seg_iter, info = _do_transcribe(with_batch=True)
                batch_used = batch_size
            except TypeError:
                seg_iter, info = _do_transcribe(with_batch=False)
                batch_used = None
        else:
            raise

    language = getattr(info, "language", None)

    for seg in seg_iter:
        start = float(seg.start)
        end = float(seg.end)
        text = (seg.text or "").strip()

        if text:
            full_text_parts.append(text)

        seg_words: List[dict] = []

        # ✅ Only collect word timestamps for SOURCE
        if use_word_ts and getattr(seg, "words", None):
            for w in seg.words:
                ww = (w.word or "").strip()
                if not ww:
                    continue
                w_start = float(w.start)
                w_end = float(w.end)

                wd = {"start": w_start, "end": w_end, "word": ww}
                seg_words.append(wd)

                flat_words.append(
                    {
                        "start": w_start,
                        "end": w_end,
                        "word": ww,
                        "seg_id": len(segments_out),
                    }
                )

        segments_out.append(
            {
                "id": len(segments_out),
                "start": start,
                "end": end,
                "text": text,
                "words": seg_words,  # empty for translate (intended)
            }
        )

        percent = int(min(100, math.floor((end * 1000) / total_ms * 100)))
        if percent > last_percent:
            pbar.update(percent - last_percent)
            last_percent = percent
            if percent >= 100 or percent - last_report_percent >= 2:
                _emit_terminal_progress(float(percent))
                last_report_percent = percent

    if last_percent < 100:
        pbar.update(100 - last_percent)
        _emit_terminal_progress(100.0)
    pbar.close()

    result = {
        "text": " ".join(full_text_parts).strip(),
        "segments": segments_out,
        "words": flat_words if use_word_ts else [],  # ✅ translate -> []
        "language": language,
        "task": task,
        "model_name": locked_model_name,
        "device": locked_device,
        "compute_type": locked_compute_type,
        "batch_size": batch_used,
        "batch_size_requested": batch_size,
        "beam_size": beam_size,
        "vad_filter": vad_filter,
        "audio_seconds": float(total_sec),
        "word_timestamps_used": use_word_ts,
        "initial_prompt": initial_prompt,
        "temperature": temperature,
        "condition_on_previous": condition_on_previous,
    }

    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


__all__ = ["transcribe"]
