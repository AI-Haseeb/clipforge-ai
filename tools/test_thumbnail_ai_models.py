from __future__ import annotations  # enables future Python language features
import argparse  # parses command-line arguments
import base64  # encodes and decodes Base64 data
import json  # handles JSON encode and decode
import os  # works with environment variables and OS paths
from pathlib import Path  # provides object-oriented file paths
import time  # measures time, delays, and elapsed seconds
import urllib.error  # handles HTTP/network exceptions
import urllib.request  # sends HTTP requests
import yaml  # reads and writes YAML config data


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "output" / "ai_model_test"
def _read_secret(path: Path) -> str:  # reads data from disk or media
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            return value
    return ""
def _load_settings() -> dict:  # loads required data/settings into memory
    settings_path = ROOT / "config" / "settings.yaml"
    if not settings_path.exists():
        return {}
    return yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
def _settings_get(settings: dict, path: list[str], default=None):  # reads a nested setting value with a safe fallback
    cur = settings or {}
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur.get(key)
    return cur
def _groq_key(settings: dict) -> str:  # reads the old Groq key only for this manual legacy thumbnail test tool
    env_name = str(_settings_get(settings, ["free_groq_meta", "api_key_env"], "GROQ_API_KEY") or "GROQ_API_KEY")
    key = os.getenv(env_name, "").strip()
    if key:
        return key
    key_file = ROOT / str(_settings_get(settings, ["free_groq_meta", "api_key_file"], "config/groq_api_key.txt"))
    return _read_secret(key_file)
def _hf_key(settings: dict) -> str:  # reads the Hugging Face token for manual thumbnail model testing
    env_name = str(_settings_get(settings, ["ai_thumbnail_generation", "hf_api_key_env"], "HF_TOKEN") or "HF_TOKEN")
    key = os.getenv(env_name, "").strip()
    if key:
        return key
    key_file = ROOT / str(_settings_get(settings, ["ai_thumbnail_generation", "hf_api_key_file"], "config/huggingface_api_key.txt"))
    return _read_secret(key_file)
def _parse_json_from_text(raw: str) -> dict:  # turns raw text/API data into structured values
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").replace("json\n", "", 1).replace("JSON\n", "", 1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    return json.loads(raw)
def make_prompt_with_groq(settings: dict, groq_key: str, topic: str, transcript: str) -> dict:  # builds a legacy Groq thumbnail prompt for manual comparison testing
    model = str(_settings_get(settings, ["free_groq_meta", "model"], "llama-3.1-8b-instant") or "llama-3.1-8b-instant")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a YouTube Shorts thumbnail art director. Return JSON only. "
                    "Create a detailed image generation prompt from the transcript."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Topic/title: {topic}\n"
                    f"Clip transcript: {transcript}\n\n"
                    "Return exactly this JSON schema:\n"
                    "{\n"
                    "  \"overlay_text\": \"2 to 5 uppercase words\",\n"
                    "  \"image_prompt\": \"detailed vertical 9:16 professional YouTube Shorts thumbnail prompt with expressive subject, high contrast background, CTR accents, text-safe space\",\n"
                    "  \"negative_prompt\": \"things to avoid\"\n"
                    "}\n"
                    "Keep overlay_text very short. Avoid copyrighted logos. Do not ask the image model to render long text."
                ),
            },
        ],
        "temperature": 0.8,
        "max_tokens": 520,
    }
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "ClipForgeAI/1.0 (+local-test)"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    content = data["choices"][0]["message"]["content"]
    prompt_json = _parse_json_from_text(content)
    prompt_json["groq_model"] = model
    return prompt_json
def generate_image_with_hf(settings: dict, hf_key: str, prompt_json: dict, output_path: Path) -> None:  # generates text, media, metadata, captions, or thumbnails
    from huggingface_hub import InferenceClient  # connects to Hugging Face models/APIs

    model = str(_settings_get(settings, ["ai_thumbnail_generation", "model"], "black-forest-labs/FLUX.1-schnell") or "black-forest-labs/FLUX.1-schnell")
    width = int(_settings_get(settings, ["ai_thumbnail_generation", "width"], 768) or 768)
    height = int(_settings_get(settings, ["ai_thumbnail_generation", "height"], 1344) or 1344)
    steps = int(_settings_get(settings, ["ai_thumbnail_generation", "steps"], 4) or 4)
    image_prompt = str(prompt_json.get("image_prompt") or "")
    negative = str(prompt_json.get("negative_prompt") or "") or None

    client = InferenceClient(
        model=model,
        provider="hf-inference",
        token=hf_key,
        timeout=240,
        headers={"User-Agent": "ClipForgeAI/1.0 (+local-test)"},
    )
    image = client.text_to_image(
        image_prompt,
        negative_prompt=negative,
        width=width,
        height=height,
        num_inference_steps=steps,
        guidance_scale=0.0,
        seed=int(time.time()),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    prompt_json["hf_model"] = model
    prompt_json["hf_provider"] = "hf-inference"
    prompt_json["output_image"] = str(output_path)
def main() -> int:  # runs this module as its command-line entry point
    parser = argparse.ArgumentParser(description="Test Groq prompt generation + Hugging Face image generation for ClipForge thumbnails.")
    parser.add_argument("--topic", default="Grow Your Business Fast")
    parser.add_argument(
        "--transcript",
        default=(
            "This short clip explains how to market a business on social media, grab attention in the first seconds, "
            "make people stop scrolling, and turn viewers into customers."
        ),
    )
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT / "groq_hf_thumbnail_test.png"))
    parser.add_argument("--skip-groq", action="store_true", help="Use a built-in thumbnail prompt and only test Hugging Face image generation.")
    args = parser.parse_args()

    settings = _load_settings()
    groq_key = _groq_key(settings)
    hf_key = _hf_key(settings)
    print(f"[test] Groq key loaded: {'yes' if groq_key else 'no'}")
    print(f"[test] Hugging Face key loaded: {'yes' if hf_key else 'no'}")
    if not groq_key:
        raise RuntimeError("Groq key missing. Expected config/groq_api_key.txt or GROQ_API_KEY.")
    if not hf_key:
        raise RuntimeError("Hugging Face key missing. Expected config/huggingface_api_key.txt or HF_TOKEN.")

    output_path = Path(args.out)
    if not output_path.is_absolute():
        output_path = ROOT / output_path

    if args.skip_groq:
        prompt_json = {
            "overlay_text": "GROW FAST",
            "image_prompt": (
                "Vertical 9:16 professional YouTube Shorts thumbnail, expressive entrepreneur looking shocked and excited, "
                "social media growth charts in background, bold yellow and white text-safe area, red arrows and circles, "
                "high contrast cinematic lighting, glossy modern creator thumbnail style, scroll-stopping composition."
            ),
            "negative_prompt": "blurry, low quality, unreadable text, watermark, logo, UI screenshot, distorted hands",
            "groq_model": "skipped",
        }
        print("[test] Groq skipped. Using built-in prompt.")
    else:
        print("[test] Sending transcript to Groq...")
        prompt_json = make_prompt_with_groq(settings, groq_key, args.topic, args.transcript)
    prompt_path = output_path.with_suffix(".prompt.json")
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(json.dumps(prompt_json, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[test] Groq OK. Overlay: {prompt_json.get('overlay_text')}")
    print(f"[test] Prompt saved: {prompt_path}")

    print("[test] Sending prompt to Hugging Face image model...")
    generate_image_with_hf(settings, hf_key, prompt_json, output_path)
    prompt_path.write_text(json.dumps(prompt_json, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[test] Hugging Face OK. Image saved: {output_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        print(f"[test] HTTP ERROR {exc.code}: {detail}")
        raise
    except urllib.error.URLError as exc:
        print(f"[test] NETWORK ERROR: {exc.reason}")
        raise
