from pathlib import Path  # provides object-oriented file paths
import json  # handles JSON encode and decode
import os  # works with environment variables and OS paths
import random  # generates random choices and variation
import time  # measures time, delays, and elapsed seconds
import urllib.error  # handles HTTP/network exceptions
import urllib.parse  # parses and encodes URL values
import urllib.request  # sends HTTP requests
import cv2  # provides OpenCV image/video processing
import numpy as np  # provides fast numeric arrays


DEFAULT_HF_IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell"
def _wrap_text(text: str, max_words_per_line: int = 3, max_lines: int = 3):  # splits thumbnail overlay text into short readable lines
    words = (text or "").upper().replace("â€”", " ").replace("-", " ").split()
    if len(words) > 9:
        words = words[:9]
    lines = []
    for i in range(0, len(words), max_words_per_line):
        lines.append(" ".join(words[i:i + max_words_per_line]))
    return lines[:max_lines] or ["WATCH THIS"]
def _settings_get(settings, path, default=None):  # reads a nested setting value with a safe fallback
    cur = settings or {}
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur.get(key)
    return cur
def _runtime_flag(settings, key: str) -> bool:  # checks a temporary per-job flag that disables repeated failed API attempts
    return isinstance(settings, dict) and bool(settings.get(key))
def _set_runtime_flag(settings, key: str) -> None:  # sets a temporary per-job flag after an API/provider failure
    if isinstance(settings, dict):
        settings[key] = True
def _read_secret_file(path: str) -> str:  # reads the first non-comment secret value from a local key file
    try:
        p = Path(path)
        if not p.exists():
            return ""
        for line in p.read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if value and not value.startswith("#"):
                return value
    except Exception:
        return ""
    return ""
def _hf_api_key(settings=None) -> str:  # finds the Hugging Face token from environment or config file
    env_name = str(_settings_get(settings, ["ai_thumbnail_generation", "hf_api_key_env"], "HF_TOKEN") or "HF_TOKEN")
    key = os.getenv(env_name, "").strip()
    if key:
        return key
    key_file = str(_settings_get(settings, ["ai_thumbnail_generation", "hf_api_key_file"], "config/huggingface_api_key.txt") or "config/huggingface_api_key.txt")
    return _read_secret_file(key_file)
def _openai_prompt_api_key(settings=None) -> str:  # finds the OpenAI key used for thumbnail prompt generation
    env_name = str(_settings_get(settings, ["openai_llm", "api_key_env"], "OPENAI_API_KEY") or "OPENAI_API_KEY")
    key = os.getenv(env_name, "").strip()
    if key:
        return key
    key_file = str(_settings_get(settings, ["openai_llm", "api_key_file"], "config/openai_api_key.txt") or "config/openai_api_key.txt")
    return _read_secret_file(key_file)
def _safe_prompt_text(text: str, limit: int = 420) -> str:  # trims prompt text so API payloads stay within a safe size
    text = " ".join(str(text or "").replace("\n", " ").split())
    return text[:limit]
def _clip_transcript_excerpt(transcript_text: str, limit: int = 900) -> str:  # creates a short transcript excerpt for thumbnail prompts
    text = " ".join(str(transcript_text or "").replace("\n", " ").split())
    return text[:limit]
def _clean_overlay_text(text: str, fallback: str = "WATCH THIS") -> str:  # converts hook/title text into a short uppercase thumbnail overlay
    text = " ".join(str(text or "").replace("\n", " ").split()).strip()
    if not text:
        text = fallback
    words = text.upper().replace("â€”", " ").replace("-", " ").split()
    words = [w.strip(".,!?;:'\"()[]{}") for w in words if w.strip(".,!?;:'\"()[]{}")]
    if len(words) > 5:
        words = words[:5]
    return " ".join(words) or fallback
def _local_thumbnail_prompt(title_text: str, variation: int = 1, transcript_text: str = "") -> str:  # builds a strong fallback thumbnail prompt from title and transcript text
    hook = _safe_prompt_text(title_text, 150) or "Stop scrolling"
    transcript = _clip_transcript_excerpt(transcript_text, 650)
    palettes = [
        "electric blue, cyan, deep black, neon lime",
        "yellow, red, black, white, high contrast",
        "magenta, purple, teal, glossy dark background",
    ]
    layouts = [
        "big emotional face, hard rim light, bold creator thumbnail, readable title block",
        "shocked reaction portrait, dramatic poster composition, viral shorts cover",
        "cinematic subject, neon glow, glossy depth, strong empty space for hook text",
    ]
    idx = max(0, min(variation - 1, 2))
    transcript_line = f" Clip transcript context: {transcript}." if transcript else ""
    return (
        "Vertical YouTube Shorts thumbnail, 9:16, high CTR creator design inspired by modern Shorts thumbnails. "
        f"Main hook: {hook}.{transcript_line} Layout: {layouts[idx]}. Palette: {palettes[idx]}. "
        "Use one expressive human subject or a clear symbolic subject that matches the transcript, surprised/emotional facial expression when appropriate, "
        "dramatic rim light, bold clean composition, strong empty space for large overlay text, glossy shadows, premium depth, cinematic contrast. "
        "Professional YouTube Shorts cover, crisp, premium, scroll-stopping, no arrows, no circles, no target marks, no pointer graphics, no watermark, no UI screenshot, no copyrighted logos."
    )
def _parse_openai_json(raw: str) -> dict:  # extracts a JSON object from OpenAI text output
    raw = (raw or "").strip()
    if not raw:
        return {}
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json\n", "", 1).replace("JSON\n", "", 1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
def _build_thumbnail_brief_with_openai(base_prompt: str, title_text: str, transcript_text: str = "", variation: int = 1, settings=None) -> dict:  # asks OpenAI for thumbnail overlay text, image prompt, and negative prompt
    fallback_overlay = _clean_overlay_text(title_text)
    brief = {
        "overlay_text": fallback_overlay,
        "image_prompt": base_prompt,
        "negative_prompt": "blurry, low quality, unreadable text, too much text, watermark, logo, UI screenshot, arrows, circles, target marks, pointer graphics, deformed face, extra fingers, distorted hands",
    }
    if _runtime_flag(settings, "_thumbnail_openai_unavailable"):
        return brief
    if not bool(_settings_get(settings, ["ai_thumbnail_generation", "use_openai_prompt"], True)):
        return brief
    api_key = _openai_prompt_api_key(settings)
    if not api_key:
        return brief

    model = str(_settings_get(settings, ["openai_llm", "model"], "gpt-4o-mini") or "gpt-4o-mini")
    transcript = _clip_transcript_excerpt(transcript_text, 1100)
    examples_style = (
        "Reference style: vertical YouTube Shorts thumbnails like the approved examples: huge 2-5 word hook text, shocked or curious face, "
        "bold yellow/white/red or neon typography, dark or bright high-contrast background, clean subject cutout, strong emotional story. "
        "Do not use arrows, circles, target marks, pointer graphics, or messy annotations."
    )
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a YouTube Shorts thumbnail art director. Return JSON only. "
                    "Create a detailed image-generation prompt from the clip transcript, not a generic prompt. "
                    "Make each variation visually different. Avoid copyrighted logos, arrows, circles, pointer graphics, and long rendered text."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Hook/title candidate: {title_text}\n"
                    f"Clip transcript/audio text: {transcript or title_text}\n"
                    f"Variation number: {variation}\n"
                    f"{examples_style}\n\n"
                    "Return this JSON schema exactly:\n"
                    "{\n"
                    "  \"overlay_text\": \"2 to 5 powerful uppercase words to draw on thumbnail\",\n"
                    "  \"image_prompt\": \"detailed 9:16 thumbnail prompt describing subject, emotion, background, colors, lighting, composition, text-safe space, CTR accents\",\n"
                    "  \"negative_prompt\": \"things to avoid\"\n"
                    "}\n"
                    "Rules: overlay_text must be short and readable. image_prompt must mention vertical 9:16, professional YouTube Shorts thumbnail, expressive subject, bold high-contrast design, clean text-safe top area, no arrows, no circles, no target marks, no pointer graphics, and the core idea from the transcript."
                ),
            },
        ],
        "temperature": 0.82,
        "max_tokens": 520,
    }
    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "ClipForgeAI/1.0 (+thumbnail-engine)"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=35) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        parsed = _parse_openai_json(data["choices"][0]["message"]["content"])
        overlay = _clean_overlay_text(parsed.get("overlay_text", ""), fallback=fallback_overlay)
        image_prompt = _safe_prompt_text(parsed.get("image_prompt", ""), 1800)
        negative = _safe_prompt_text(parsed.get("negative_prompt", ""), 500)
        if image_prompt:
            brief["overlay_text"] = overlay
            brief["image_prompt"] = image_prompt
            if negative:
                brief["negative_prompt"] = negative
            print(f"   [thumbnail-ai] OpenAI thumbnail brief: {overlay}", flush=True)
        return brief
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            _set_runtime_flag(settings, "_thumbnail_openai_unavailable")
            print(f"   [thumbnail-ai] OpenAI thumbnail brief disabled for this job: HTTP {e.code}. Check OPENAI_API_KEY/config/openai_api_key.txt.", flush=True)
        else:
            print(f"   [thumbnail-ai] OpenAI thumbnail brief skipped: HTTP {e.code}", flush=True)
        return brief
    except urllib.error.URLError as e:
        _set_runtime_flag(settings, "_thumbnail_openai_unavailable")
        print(f"   [thumbnail-ai] OpenAI thumbnail brief disabled for this job: network unavailable ({e.reason}).", flush=True)
        return brief
    except Exception as e:
        print(f"   [thumbnail-ai] OpenAI thumbnail brief skipped: {e}", flush=True)
        return brief
def _prompt_with_negative(brief: dict) -> str:  # combines the positive prompt and negative prompt for image generation
    prompt = str(brief.get("image_prompt") or "")
    negative = str(brief.get("negative_prompt") or "")
    if negative:
        prompt += " Negative prompt: " + negative
    return prompt
def _write_thumbnail_brief_file(image_path: Path, brief: dict, variation: int) -> None:  # saves the prompt/overlay data next to the generated thumbnail
    try:
        brief_path = image_path.with_name(f"{image_path.stem}_prompt.json")
        payload = dict(brief)
        payload["variation"] = variation
        brief_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
def _hf_generate_image(prompt: str, output_path: Path, settings=None, variation: int = 1) -> bool:  # calls Hugging Face image inference to create a thumbnail image
    if not bool(_settings_get(settings, ["ai_thumbnail_generation", "hf_enabled"], True)):
        _set_runtime_flag(settings, "_thumbnail_hf_unavailable")
        return False
    if _runtime_flag(settings, "_thumbnail_hf_unavailable"):
        return False
    api_key = _hf_api_key(settings)
    if not api_key:
        _set_runtime_flag(settings, "_thumbnail_hf_unavailable")
        print("   [thumbnail-ai] HF disabled for this job: token missing. Add config/huggingface_api_key.txt or HF_TOKEN.", flush=True)
        return False

    model = str(_settings_get(settings, ["ai_thumbnail_generation", "model"], DEFAULT_HF_IMAGE_MODEL) or DEFAULT_HF_IMAGE_MODEL)
    provider = str(_settings_get(settings, ["ai_thumbnail_generation", "provider"], "hf-inference") or "hf-inference")
    if provider == "huggingface":
        provider = "hf-inference"
    width = int(_settings_get(settings, ["ai_thumbnail_generation", "width"], 768) or 768)
    height = int(_settings_get(settings, ["ai_thumbnail_generation", "height"], 1344) or 1344)
    steps = int(_settings_get(settings, ["ai_thumbnail_generation", "steps"], 4) or 4)
    retries = int(_settings_get(settings, ["ai_thumbnail_generation", "retries"], 2) or 2)

    for attempt in range(1, retries + 2):
        try:
            from huggingface_hub import InferenceClient  # connects to Hugging Face models/APIs

            client = InferenceClient(
                model=model,
                provider=provider,
                token=api_key,
                timeout=240,
                headers={"User-Agent": "ClipForgeAI/1.0 (+thumbnail-engine)"},
            )
            image_prompt, negative_prompt = _split_prompt_negative(prompt)
            image = client.text_to_image(
                image_prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                num_inference_steps=steps,
                guidance_scale=0.0,
                seed=int(time.time()) + variation * 997,
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(output_path)
            return True
        except Exception as e:
            msg = str(e)
            print(f"   [thumbnail-ai] HF attempt {attempt} failed: {msg[:500]}", flush=True)
            if "401" in msg or "403" in msg:
                _set_runtime_flag(settings, "_thumbnail_hf_unavailable")
                print("   [thumbnail-ai] HF disabled for this job: authorization failed.", flush=True)
                break
            if "402" in msg or "Payment Required" in msg or "depleted your monthly included credits" in msg:
                _set_runtime_flag(settings, "_thumbnail_hf_unavailable")
                print("   [thumbnail-ai] HF disabled for this job: monthly included credits are depleted.", flush=True)
                break
            if "410" in msg or "Gone" in msg or "deprecated" in msg or "no longer supported" in msg:
                _set_runtime_flag(settings, "_thumbnail_hf_unavailable")
                print("   [thumbnail-ai] HF disabled for this job: selected image model/provider is no longer supported; using free/local fallback.", flush=True)
                break
            if "getaddrinfo failed" in msg or "NameResolutionError" in msg:
                _set_runtime_flag(settings, "_thumbnail_hf_unavailable")
                print("   [thumbnail-ai] HF disabled for this job: network/DNS unavailable.", flush=True)
                break
        if attempt <= retries and not _runtime_flag(settings, "_thumbnail_hf_unavailable"):
            time.sleep(2 * attempt)
    return False
def _split_prompt_negative(prompt: str) -> tuple[str, str | None]:  # separates negative prompt instructions from the main prompt
    image_prompt = str(prompt or "")
    marker = " Negative prompt: "
    if marker in image_prompt:
        image_prompt, negative_prompt = image_prompt.split(marker, 1)
        return image_prompt, negative_prompt
    return image_prompt, None
def _free_generate_image(prompt: str, output_path: Path, settings=None, variation: int = 1) -> bool:  # tries the free image-generation fallback provider
    if _runtime_flag(settings, "_thumbnail_free_image_unavailable"):
        return False
    if not bool(_settings_get(settings, ["ai_thumbnail_generation", "free_fallback_enabled"], True)):
        return False

    width = int(_settings_get(settings, ["ai_thumbnail_generation", "width"], 768) or 768)
    height = int(_settings_get(settings, ["ai_thumbnail_generation", "height"], 1344) or 1344)
    model = str(_settings_get(settings, ["ai_thumbnail_generation", "free_fallback_model"], "flux") or "flux")
    image_prompt, negative_prompt = _split_prompt_negative(prompt)
    final_prompt = (
        image_prompt
        + " Full AI-generated vertical YouTube Shorts thumbnail, huge readable hook text area, shocked or emotional subject, "
        + "premium red/yellow/black or neon high-CTR style, glossy creator thumbnail, no arrows, no circles, no logos, no watermark."
    )
    if negative_prompt:
        final_prompt += " Avoid: " + negative_prompt

    params = {
        "width": str(width),
        "height": str(height),
        "model": model,
        "nologo": "true",
        "private": "true",
        "seed": str(int(time.time()) + variation * 997),
    }
    query = urllib.parse.urlencode(params)
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(final_prompt[:1800]) + "?" + query

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 ClipForgeAI/1.0 (+thumbnail-free-fallback)", "Accept": "image/*"},
        )
        with urllib.request.urlopen(req, timeout=240) as resp:
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read()
        if "image" not in content_type.lower() or not body:
            raise RuntimeError(f"non-image response: {content_type}")
        from io import BytesIO  # handles in-memory streams
        from PIL import Image  # provides image drawing and editing tools

        output_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.open(BytesIO(body)).convert("RGB")
        image.save(output_path)
        print("   [thumbnail-ai] Free full-image generator created thumbnail.", flush=True)
        return True
    except Exception as e:
        _set_runtime_flag(settings, "_thumbnail_free_image_unavailable")
        print(f"   [thumbnail-ai] Free full-image generator unavailable: {str(e)[:300]}", flush=True)
        return False
def _draw_text_with_outline(img, text, x, y, font, scale, color, thickness, shadow=(0, 0, 0)):  # draws readable outlined text onto a thumbnail image
    cv2.putText(img, text, (x + 7, y + 8), font, scale, shadow, thickness + 8, cv2.LINE_AA)
    cv2.putText(img, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)
def _fit_text_scale(text, font, max_width, start_scale, thickness):  # chooses a font scale that fits text inside a target width
    scale = start_scale
    while scale > 0.75:
        (tw, _), _ = cv2.getTextSize(text, font, scale, thickness)
        if tw <= max_width:
            return scale
        scale -= 0.08
    return scale
def _read_best_frame(video_path: Path, width: int, height: int):  # reads a useful frame from the source video for local thumbnail fallback
    cap = cv2.VideoCapture(str(video_path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total <= 0:
        cap.release()
        return None
    candidates = []
    sample_points = (0.06, 0.10, 0.15, 0.22, 0.31, 0.42, 0.55, 0.68, 0.82, 0.92)
    face_cascade = None
    try:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        face_cascade = cv2.CascadeClassifier(cascade_path)
        if face_cascade.empty():
            face_cascade = None
    except Exception:
        face_cascade = None

    for pct in sample_points:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(total * pct)))
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        frame = cv2.resize(frame, (width, height))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
        brightness = float(gray.mean())
        contrast = float(gray.std())
        exposure_score = max(0.0, 120.0 - abs(brightness - 118.0)) * 7.0
        face_score = 0.0
        if face_cascade is not None:
            small = cv2.resize(gray, (max(1, width // 4), max(1, height // 4)))
            faces = face_cascade.detectMultiScale(small, scaleFactor=1.08, minNeighbors=4, minSize=(28, 28))
            if len(faces):
                largest = max((fw * fh for (_x, _y, fw, fh) in faces), default=0)
                face_score = 850.0 + min(1300.0, largest * 0.16)
        score = sharpness + contrast * 12.0 + exposure_score + face_score
        candidates.append((score, frame))
    cap.release()
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]
def _cover_resize(img, width, height):  # resizes/crops an image so it fills the target thumbnail canvas
    h, w = img.shape[:2]
    scale = max(width / w, height / h)
    nw, nh = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (nw, nh))
    x = max(0, (nw - width) // 2)
    y = max(0, (nh - height) // 2)
    return resized[y:y + height, x:x + width]
def _make_background(frame, width, height, variation):  # creates a stylized thumbnail background from a video frame
    bg = _cover_resize(frame, width, height)
    bg = cv2.convertScaleAbs(bg, alpha=1.08, beta=4)
    blurred = cv2.GaussianBlur(bg, (0, 0), 24)
    washes = [(14, 54, 125), (15, 34, 120), (78, 28, 92)]
    color_wash = np.zeros_like(bg)
    color_wash[:] = washes[(variation - 1) % 3]
    bg = cv2.addWeighted(blurred, 0.66, color_wash, 0.34, 0)
    vignette = np.zeros((height, width), dtype=np.uint8)
    cv2.circle(vignette, (width // 2, int(height * 0.48)), int(height * 0.62), 255, -1)
    vignette = cv2.GaussianBlur(vignette, (0, 0), 180) / 255.0
    bg = (bg * (0.42 + 0.58 * vignette[..., None])).astype(np.uint8)
    return bg
def _paste_subject(canvas, frame, variation):  # places the actual clip frame prominently onto the thumbnail canvas
    h, w = canvas.shape[:2]
    subject = _cover_resize(frame, int(w * 0.96), int(h * 0.70))
    subject = cv2.convertScaleAbs(subject, alpha=1.20, beta=10)
    blur = cv2.GaussianBlur(subject, (0, 0), 1.4)
    subject = cv2.addWeighted(subject, 1.35, blur, -0.35, 0)
    sh, sw = subject.shape[:2]
    x = int(w * 0.02)
    y = int(h * (0.24 if variation == 1 else 0.25 if variation == 2 else 0.27))
    x2, y2 = min(w, x + sw), min(h, y + sh)
    subject = subject[:y2 - y, :x2 - x]
    canvas[y:y2, x:x2] = cv2.addWeighted(canvas[y:y2, x:x2], 0.08, subject, 0.92, 0)
    shade = canvas.copy()
    cv2.rectangle(shade, (0, y), (w, min(h, y + 170)), (0, 0, 0), -1)
    cv2.rectangle(shade, (0, max(0, y2 - 190)), (w, y2), (0, 0, 0), -1)
    cv2.addWeighted(shade, 0.22, canvas, 0.78, 0, canvas)
    accent = [(0, 255, 255), (0, 120, 255), (255, 80, 255)][(variation - 1) % 3]
    cv2.rectangle(canvas, (x + 12, y + 12), (x2 - 12, y2 - 12), accent, 4, cv2.LINE_AA)
    return canvas
def _draw_rounded_rect(img, x1, y1, x2, y2, color, radius=30, alpha=1.0):  # draws a rounded rectangle behind thumbnail text or accents
    overlay = img.copy()
    cv2.rectangle(overlay, (x1 + radius, y1), (x2 - radius, y2), color, -1)
    cv2.rectangle(overlay, (x1, y1 + radius), (x2, y2 - radius), color, -1)
    cv2.circle(overlay, (x1 + radius, y1 + radius), radius, color, -1)
    cv2.circle(overlay, (x2 - radius, y1 + radius), radius, color, -1)
    cv2.circle(overlay, (x1 + radius, y2 - radius), radius, color, -1)
    cv2.circle(overlay, (x2 - radius, y2 - radius), radius, color, -1)
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)
def _draw_professional_text(canvas, title_text, variation):  # draws the final high-contrast thumbnail title treatment
    h, w = canvas.shape[:2]
    font = cv2.FONT_HERSHEY_DUPLEX
    palettes = [
        ((0, 255, 255), (255, 255, 255), (20, 20, 20)),
        ((0, 245, 255), (255, 255, 255), (12, 22, 170)),
        ((255, 90, 255), (255, 255, 255), (12, 45, 80)),
    ]
    accent, white, box = palettes[(variation - 1) % 3]
    lines = _wrap_text(title_text, max_words_per_line=2 if variation == 2 else 3, max_lines=3)

    _draw_rounded_rect(canvas, 55, 72, w - 55, 440, box, radius=38, alpha=0.88)
    cv2.rectangle(canvas, (85, 105), (w - 85, 115), accent, -1)

    y = 205
    for idx, line in enumerate(lines):
        thickness = 8 if idx == 0 else 7
        start_scale = 2.25 if idx == 0 else 2.05
        scale = _fit_text_scale(line, font, w - 150, start_scale, thickness)
        (tw, _), _ = cv2.getTextSize(line, font, scale, thickness)
        x = max(45, (w - tw) // 2)
        color = accent if idx == 0 else white
        _draw_text_with_outline(canvas, line, x, y, font, scale, color, thickness)
        y += int(92 * scale / 1.7)

    badge_text = ["VIRAL CLIP", "WAIT FOR IT", "REAL MOMENT"][(variation - 1) % 3]
    _draw_rounded_rect(canvas, 72, h - 255, 430, h - 160, (0, 0, 0), radius=28, alpha=0.82)
    _draw_text_with_outline(canvas, badge_text, 105, h - 190, font, 1.05, accent, 4)

    cta_text = ["DON'T MISS THIS", "WATCH NOW", "SEE WHAT HAPPENS"][(variation - 1) % 3]
    _draw_rounded_rect(canvas, 0, h - 128, w, h, (18, 20, 205), radius=0, alpha=0.95)
    scale = _fit_text_scale(cta_text, font, w - 100, 1.55, 5)
    (ctw, _), _ = cv2.getTextSize(cta_text, font, scale, 5)
    _draw_text_with_outline(canvas, cta_text, max(45, (w - ctw) // 2), h - 43, font, scale, white, 5)

    # Keep the approved thumbnail style clean: no arrows, circles, or pointer marks.
    return canvas
def _create_local_thumbnail(video_path, title_text, output_path, width=1080, height=1920, variation=1):  # builds a local thumbnail using video frame, colors, and overlay text
    video_path = Path(video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame = _read_best_frame(video_path, width, height)
    if frame is None:
        return None
    canvas = _make_background(frame, width, height, variation)
    canvas = _paste_subject(canvas, frame, variation)
    canvas = _draw_professional_text(canvas, title_text, variation)
    if output_path.suffix.lower() == ".png":
        cv2.imwrite(str(output_path), canvas, [cv2.IMWRITE_PNG_COMPRESSION, 3])
    else:
        cv2.imwrite(str(output_path), canvas, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return output_path
def _postprocess_generated_thumbnail(image_path: Path, title_text: str, variation: int = 1) -> None:  # adds final overlay text treatment to an AI-generated thumbnail
    img = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if img is None:
        return
    height, width = 1920, 1080
    img = cv2.resize(img, (width, height))
    top_overlay = img.copy()
    cv2.rectangle(top_overlay, (0, 0), (width, 470), (0, 0, 0), -1)
    img = cv2.addWeighted(top_overlay, 0.48, img, 0.52, 0)
    img = _draw_professional_text(img, title_text, variation)
    cv2.imwrite(str(image_path), img, [cv2.IMWRITE_PNG_COMPRESSION, 3])
def create_thumbnail_for_short(  # creates thumbnail variants using OpenAI prompts, HF/free image generation, or local fallback
    video_path,
    title_text,
    output_path,
    width: int = 1080,
    height: int = 1920,
    settings=None,
    variations: int | None = None,
    transcript_text: str = "",
):
    ai_cfg = (settings or {}).get("ai_thumbnail_generation", {}) if isinstance(settings, dict) else {}
    ai_enabled = bool(ai_cfg.get("enabled", False))
    count = int(variations or (ai_cfg.get("variations", 3) if ai_enabled else 1) or 1)
    count = max(1, min(5, count))
    output_path = Path(output_path)

    if ai_enabled:
        created = []
        for idx in range(1, count + 1):
            variant_path = output_path if idx == 1 else output_path.with_name(f"{output_path.stem}_v{idx}{output_path.suffix}")
            base_prompt = _local_thumbnail_prompt(title_text, idx, transcript_text=transcript_text)
            brief = _build_thumbnail_brief_with_openai(
                base_prompt=base_prompt,
                title_text=title_text,
                transcript_text=transcript_text,
                variation=idx,
                settings=settings,
            )
            prompt = _prompt_with_negative(brief)
            overlay_text = brief.get("overlay_text") or title_text
            _write_thumbnail_brief_file(variant_path, brief, idx)
            if _hf_generate_image(prompt, variant_path, settings=settings, variation=idx) or _free_generate_image(prompt, variant_path, settings=settings, variation=idx):
                _postprocess_generated_thumbnail(variant_path, overlay_text, idx)
                created.append(variant_path)
        if created:
            return created[0]
        print("   [thumbnail-ai] Falling back to local professional thumbnail renderer.", flush=True)

    first = None
    for idx in range(1, count + 1):
        variant_path = output_path if idx == 1 else output_path.with_name(f"{output_path.stem}_v{idx}{output_path.suffix}")
        base_prompt = _local_thumbnail_prompt(title_text, idx, transcript_text=transcript_text)
        brief = _build_thumbnail_brief_with_openai(
            base_prompt=base_prompt,
            title_text=title_text,
            transcript_text=transcript_text,
            variation=idx,
            settings=settings,
        )
        overlay_text = brief.get("overlay_text") or title_text
        _write_thumbnail_brief_file(variant_path, brief, idx)
        made = _create_local_thumbnail(video_path, overlay_text, variant_path, width=width, height=height, variation=idx)
        if made and first is None:
            first = made
    return first





