from __future__ import annotations  # enables future Python language features
import os  # works with environment variables and OS paths
import re  # matches and cleans text with regular expressions
import hashlib  # creates cryptographic hashes
from pathlib import Path  # provides object-oriented file paths
from typing import Any, Dict, List, Tuple, Optional  # adds type hint helpers
import numpy as np  # provides fast numeric arrays
from src.pipeline.detect_highlights import score_text  # project helper module


# =========================
# Public API
# =========================
def pick_segments_semantic(  # chooses a matching preset, track, or fallback
    whisper_result: dict,
    keywords: List[Tuple[str, float]],
    min_len: int,
    max_len: int,
    max_shorts: int,
    settings: Dict[str, Any],
) -> List[dict]:
    """
    Meaning-first semantic clip picker.

    Returns segments in the downstream-safe schema:
    {
      "start": float,
      "end": float,
      "duration": float,
      "text": str,
      "score": float,
      "source": "semantic",
      ...score_* debug fields...
    }
    """
    cfg = (settings or {}).get("semantic_highlights", {}) or {}
    debug = bool(cfg.get("debug", True))
    def log(msg: str) -> None:# prints or stores a debug log message
        if debug:
            print(f"[semantic-ai] {msg}")

    if not bool(cfg.get("enabled", False)):
        log("DISABLED: semantic_highlights.enabled is false. Falling back to existing highlight logic.")
        return []

    segs = whisper_result.get("segments", []) or []
    if not segs:
        log("FALLBACK: Whisper result has no segments.")
        return []

    max_candidates = int(cfg.get("max_candidates", 180))
    top_k = int(cfg.get("top_k", max_shorts))
    lam = float(cfg.get("lambda_diversity", 0.35))
    max_similarity = float(cfg.get("max_selected_similarity", 0.86))
    max_temporal_overlap = float(cfg.get("max_temporal_overlap", 0.55))
    min_final = float(cfg.get("min_final_score", 0.42))
    min_hook = float(cfg.get("min_hook_score", 0.28))
    min_complete = float(cfg.get("min_completeness_score", 0.34))
    min_retention = float(cfg.get("min_retention_score", 0.28))
    min_takeaway = float(cfg.get("min_takeaway_score", 0.25))

    model_name = str(cfg.get("model_name", "sentence-transformers/all-MiniLM-L6-v2"))
    device = str(cfg.get("device", "cpu"))
    batch_size = int(cfg.get("batch_size", 32))

    min_len = int(max(1, min_len))
    max_len = int(max(min_len + 1, max_len))
    max_shorts = int(max(1, max_shorts))
    top_k = int(max(1, min(top_k, max_shorts)))

    candidates: List[dict] = []
    n = len(segs)

    for i in range(0, n, 1):
        start = float(segs[i].get("start", 0.0) or 0.0)
        parts: List[str] = []
        end = start

        for j in range(i, n):
            end = float(segs[j].get("end", start) or start)
            dur = float(end - start)
            if dur <= 0:
                continue
            if dur > max_len:
                break

            txt = _seg_text(segs[j])
            if txt:
                parts.append(txt)

            if dur < min_len:
                continue

            clip_text = " ".join(parts).strip()
            if _word_count(clip_text) < 10:
                _debug_reject(log, start, end, "too few words", 0.0)
                continue

            early_text = _window_text(segs, start, min(end, start + 5.0)) or clip_text[:180]
            candidate = {
                "embedding_index": len(candidates),
                "start": start,
                "end": end,
                "duration": dur,
                "text": clip_text,
                "early_text": early_text,
                "start_index": i,
                "end_index": j,
                "score": 0.0,
                "source": "semantic",
            }
            candidates.append(candidate)

            if len(candidates) >= max_candidates:
                break
        if len(candidates) >= max_candidates:
            break

    if not candidates:
        log("FALLBACK: no candidate windows were built from transcript.")
        return []

    texts = [c["text"] for c in candidates]
    full_text = " ".join(_seg_text(s) for s in segs).strip()

    try:
        mat = _embed_matrix(
            texts=texts,
            model_name=model_name,
            device=device,
            batch_size=batch_size,
            settings=settings,
            cache_tag="candidates",
        )
        full_vec = _embed_matrix(
            texts=[full_text or " "],
            model_name=model_name,
            device=device,
            batch_size=batch_size,
            settings=settings,
            cache_tag="full",
        )[0]
    except Exception as e:
        log(f"FALLBACK: embedding model failed ({type(e).__name__}: {e}).")
        return []

    sims_to_full = (mat @ full_vec.reshape(-1, 1)).reshape(-1)
    sim_matrix = mat @ mat.T

    scored: List[dict] = []
    for i, c in enumerate(candidates):
        text_value = c["text"]
        early_text = c.get("early_text", "")
        dur = float(c["duration"])

        keyword_score_raw = float(score_text(text_value, keywords))
        keyword_score = _keyword_quality_score(keyword_score_raw, keywords)
        hook_score = _hook_score(early_text, text_value, keywords)
        completeness_score, completeness_reasons, takeaway_score = _completeness_score(c, segs)
        emotion_energy_score = _emotion_energy_score(text_value)
        salience_score = float(_clamp01((float(sims_to_full[i]) + 1.0) / 2.0))

        if len(candidates) > 1:
            avg_sim = (float(np.sum(sim_matrix[i])) - 1.0) / max(1, len(candidates) - 1)
        else:
            avg_sim = 0.0
        novelty_score = float(_clamp01(1.0 - max(0.0, avg_sim)))
        retention_score, retention_reasons = _retention_score(text_value, dur, c["start"], c["end"], segs)

        final_score = (
            0.30 * hook_score
            + 0.20 * completeness_score
            + 0.15 * emotion_energy_score
            + 0.15 * keyword_score
            + 0.10 * salience_score
            + 0.05 * novelty_score
            + 0.05 * retention_score
        )

        reasons: List[str] = []
        if _starts_mid_sentence(text_value, int(c["start_index"])):
            reasons.append("starts mid-sentence")
        if _ends_mid_sentence(text_value):
            reasons.append("ends mid-sentence")
        if hook_score < min_hook:
            reasons.append("first 5 seconds are weak")
        if completeness_score < min_complete:
            reasons.append("no clear start/middle/end")
        if takeaway_score < min_takeaway:
            reasons.append("no clear takeaway")
        if retention_score < min_retention:
            reasons.extend(retention_reasons or ["low retention"])
        if final_score < min_final:
            reasons.append("final score below threshold")
        reasons.extend(completeness_reasons)

        c.update(
            {
                "score": float(round(final_score, 4)),
                "score_hook": float(round(hook_score, 4)),
                "score_completeness": float(round(completeness_score, 4)),
                "score_emotion_energy": float(round(emotion_energy_score, 4)),
                "score_keyword": float(round(keyword_score, 4)),
                "score_keyword_raw": float(round(keyword_score_raw, 4)),
                "score_salience": float(round(salience_score, 4)),
                "score_novelty": float(round(novelty_score, 4)),
                "score_retention": float(round(retention_score, 4)),
                "score_takeaway": float(round(takeaway_score, 4)),
                "reject_reasons": sorted(set(reasons)),
            }
        )

        if reasons:
            _debug_reject(log, c["start"], c["end"], "; ".join(sorted(set(reasons))), final_score)
            continue

        scored.append(c)

    if not scored:
        log(f"FALLBACK: all {len(candidates)} semantic candidates were rejected by quality gates.")
        return []

    selected = _mmr_select(
        candidates=scored,
        mat=mat[[int(c["embedding_index"]) for c in scored]],
        top_k=top_k,
        lambda_diversity=float(lam),
        max_similarity=max_similarity,
        max_temporal_overlap=max_temporal_overlap,
        debug=debug,
    )

    if not selected:
        log("FALLBACK: MMR rejected every semantic candidate as duplicate/similar.")
        return []

    out = [_sanitize_segment(x, source="semantic") for x in selected]
    out.sort(key=lambda x: float(x["start"]))
    for c in out:
        log(
            "SELECT "
            f"{c['start']:.2f}-{c['end']:.2f}s score={float(c['score']):.3f} "
            f"hook={float(c.get('score_hook', 0.0)):.2f} "
            f"complete={float(c.get('score_completeness', 0.0)):.2f} "
            f"emotion={float(c.get('score_emotion_energy', 0.0)):.2f} "
            f"keyword={float(c.get('score_keyword', 0.0)):.2f} "
            f"salience={float(c.get('score_salience', 0.0)):.2f} "
            f"novelty={float(c.get('score_novelty', 0.0)):.2f} "
            f"retention={float(c.get('score_retention', 0.0)):.2f}"
        )
    return out
def merge_segments(rule_based: List[dict], semantic: List[dict]) -> List[dict]:# builds clip segment data for merge segments
    """
    Merges segments from rule-based + semantic.
    - removes near-duplicates using IoU overlap
    - keeps higher score
    - guarantees schema fields for downstream cut_all()
    """
    items = (rule_based or []) + (semantic or [])
    if not items:
        return []

    # sanitize all inputs (rule based may not have score/text/source)
    clean: List[dict] = []
    for x in items:
        src = (x.get("source") or ("semantic" if x in (semantic or []) else "rule")).strip().lower()
        clean.append(_sanitize_segment(x, source=src))

    # prefer higher score first
    clean.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
    def iou(a: dict, b: dict) -> float:# calculates overlap between two time ranges or boxes
        s1, e1 = float(a["start"]), float(a["end"])
        s2, e2 = float(b["start"]), float(b["end"])
        inter = max(0.0, min(e1, e2) - max(s1, s2))
        union = max(1e-6, max(e1, e2) - min(s1, s2))
        return inter / union

    merged: List[dict] = []
    for item in clean:
        if all(iou(item, m) < 0.55 for m in merged):
            merged.append(item)

    merged.sort(key=lambda x: float(x["start"]))
    return merged


# =========================
# Internal helpers
# =========================
def _seg_text(seg: dict) -> str:# handles seg text behavior
    return (seg.get("text") or "").strip()
def _window_text(segs: List[dict], start: float, end: float) -> str:# handles window text behavior
    parts: List[str] = []
    for seg in segs:
        s = float(seg.get("start", 0.0) or 0.0)
        e = float(seg.get("end", s) or s)
        if e <= start:
            continue
        if s >= end:
            break
        txt = _seg_text(seg)
        if txt:
            parts.append(txt)
    return " ".join(parts).strip()
def _debug_reject(log, start: float, end: float, reason: str, score: float) -> None:# handles debug reject behavior
    log(f"REJECT {float(start):.2f}-{float(end):.2f}s score={float(score):.3f} reason={reason}")
def _keyword_quality_score(raw_score: float, keywords: List[Tuple[str, float]]) -> float:# calculates the keyword quality score score
    if not keywords:
        return 0.45
    return float(_clamp01(raw_score / 8.0))
def _hook_score(early_text: str, full_text: str, keywords: List[Tuple[str, float]]) -> float:# calculates the hook score score
    early = _norm_text(early_text)
    full = _norm_text(full_text)
    if not early:
        return 0.0

    wc = _word_count(early_text)
    score = 0.22
    if wc >= 6:
        score += 0.12
    if wc >= 12:
        score += 0.08
    if "?" in early_text:
        score += 0.12
    if "!" in early_text:
        score += 0.08

    hook_terms = (
        "stop", "wait", "listen", "look", "secret", "mistake", "wrong", "truth",
        "important", "problem", "reason", "never", "always", "how", "why",
        "agar", "ruk", "dekho", "galti", "sach", "zaroori", "scene", "point",
    )
    if any(term in early for term in hook_terms):
        score += 0.22
    if re.search(r"\b\d+\b", early):
        score += 0.08
    if any(_norm_text(kw) in early for kw, _ in (keywords or []) if _norm_text(kw)):
        score += 0.16

    weak_terms = ("um", "uh", "you know", "basically", "actually", "literally")
    if any(term in early for term in weak_terms):
        score -= 0.12
    if _repetition_ratio(full) > 0.34:
        score -= 0.08
    return float(_clamp01(score))
def _completeness_score(candidate: dict, segs: List[dict]) -> Tuple[float, List[str], float]:# calculates the completeness score score
    text_value = candidate.get("text", "")
    start_idx = int(candidate.get("start_index", 0) or 0)
    dur = float(candidate.get("duration", 0.0) or 0.0)
    wc = _word_count(text_value)
    norm = _norm_text(text_value)
    reasons: List[str] = []

    start_ok = 0.0 if _starts_mid_sentence(text_value, start_idx) else 1.0
    end_ok = 0.0 if _ends_mid_sentence(text_value) else 1.0
    length_ok = _clamp01((wc - 10) / 45.0)

    takeaway_terms = (
        "so", "therefore", "because", "that means", "this means", "lesson", "takeaway",
        "remember", "save", "share", "result", "solution", "finally", "in short",
        "matlab", "is liye", "iska matlab", "lesson", "yaad", "natija", "hal", "akhir",
    )
    takeaway_score = 0.25
    if any(term in norm for term in takeaway_terms):
        takeaway_score += 0.45
    if re.search(r"[.!?]\s*$", text_value.strip()):
        takeaway_score += 0.20
    if wc >= 25:
        takeaway_score += 0.10
    takeaway_score = float(_clamp01(takeaway_score))

    if start_ok < 1.0:
        reasons.append("weak opening boundary")
    if end_ok < 1.0:
        reasons.append("weak ending boundary")
    if dur < 12:
        reasons.append("clip too short for complete idea")

    score = 0.30 * start_ok + 0.25 * end_ok + 0.20 * length_ok + 0.25 * takeaway_score
    return float(_clamp01(score)), reasons, takeaway_score
def _emotion_energy_score(text_value: str) -> float:# calculates the emotion energy score score
    norm = _norm_text(text_value)
    wc = _word_count(text_value)
    score = 0.28
    emotion_terms = (
        "love", "hate", "fear", "pain", "sad", "happy", "excited", "serious", "shocking",
        "crazy", "amazing", "hard", "struggle", "win", "fail", "risk", "money", "growth",
        "dard", "khushi", "dar", "serious", "shock", "kamal", "mushkil", "jeet", "haar",
        "risk", "paisa", "growth", "success", "failure",
    )
    high_value_terms = (
        "how", "why", "lesson", "strategy", "tip", "mistake", "secret", "truth", "framework",
        "kaise", "kyu", "lesson", "strategy", "tip", "galti", "sach", "formula",
    )
    score += min(0.30, 0.06 * sum(1 for term in emotion_terms if term in norm))
    score += min(0.24, 0.06 * sum(1 for term in high_value_terms if term in norm))
    score += min(0.10, text_value.count("!") * 0.05)
    score += min(0.08, text_value.count("?") * 0.04)
    if wc >= 25:
        score += 0.08
    return float(_clamp01(score))
def _retention_score(text_value: str, duration: float, start: float, end: float, segs: List[dict]) -> Tuple[float, List[str]]:# calculates the retention score score
    reasons: List[str] = []
    wc = _word_count(text_value)
    wps = wc / max(0.01, float(duration))
    pacing = _clamp01(1.0 - abs(wps - 2.35) / 2.35)
    repetition = _repetition_ratio(text_value)
    silence_ratio = _silence_ratio(start, end, segs)

    score = 0.55 * pacing + 0.25 * (1.0 - repetition) + 0.20 * (1.0 - silence_ratio)
    if wps < 0.75:
        reasons.append("too slow or sparse")
    if repetition > 0.38:
        reasons.append("too repetitive")
    if silence_ratio > 0.35:
        reasons.append("too much silence")
    return float(_clamp01(score)), reasons
def _starts_mid_sentence(text_value: str, start_index: int) -> bool:  # starts a job, process, worker, or timer
    stripped = (text_value or "").strip()
    if not stripped or start_index <= 0:
        return False
    first = _norm_text(stripped.split()[0]) if stripped.split() else ""
    mid_words = {
        "and", "but", "or", "so", "because", "that", "then", "which", "when", "while",
        "aur", "lekin", "magar", "kyunki", "ke", "phir", "jo", "jab", "agar",
    }
    if first in mid_words:
        return True
    return False
def _ends_mid_sentence(text_value: str) -> bool:# handles ends mid sentence behavior
    stripped = (text_value or "").strip()
    if not stripped:
        return True
    if re.search(r"[.!?]\s*$", stripped):
        return False
    tail = _norm_text(" ".join(stripped.split()[-3:]))
    incomplete_endings = (
        "and", "but", "or", "because", "so", "that", "to", "for", "with", "without",
        "aur", "lekin", "kyunki", "ke", "to", "phir", "jab", "agar",
    )
    return any(tail.endswith(" " + term) or tail == term for term in incomplete_endings)
def _silence_ratio(start: float, end: float, segs: List[dict]) -> float:# calculates the silence ratio ratio
    duration = max(0.01, float(end) - float(start))
    gaps: List[float] = []
    prev_end: Optional[float] = None
    for seg in segs:
        s = float(seg.get("start", 0.0) or 0.0)
        e = float(seg.get("end", s) or s)
        if e <= start:
            continue
        if s >= end:
            break
        s = max(s, start)
        e = min(e, end)
        if prev_end is not None and s > prev_end:
            gaps.append(s - prev_end)
        prev_end = max(prev_end or s, e)
    long_silence = sum(max(0.0, g - 0.45) for g in gaps)
    return float(_clamp01(long_silence / duration))
def _repetition_ratio(text_value: str) -> float:# calculates the repetition ratio ratio
    words = [_norm_text(w) for w in re.findall(r"[A-Za-z0-9']+", text_value or "")]
    words = [w for w in words if len(w) > 2]
    if not words:
        return 0.0
    unique = len(set(words))
    return float(_clamp01(1.0 - unique / max(1, len(words))))
def _norm_text(text_value: str) -> str:# normalizes text text/value for consistent matching
    return re.sub(r"\s+", " ", (text_value or "").lower()).strip()
def _sanitize_segment(x: dict, source: str) -> dict:# sanitizes segment so it is safe to use
    s = float(x.get("start", 0.0))
    e = float(x.get("end", s))
    if e < s:
        s, e = e, s
    text = (x.get("text") or "").strip()
    score = float(x.get("score", x.get("score_keyword", 0.0)) or 0.0)

    out = dict(x)
    out["start"] = float(s)
    out["end"] = float(e)
    out["duration"] = float(max(0.0, e - s))
    out["text"] = text
    out["score"] = score
    out["source"] = (source or out.get("source") or "rule").strip().lower()
    return out
def _cache_dir(settings: Dict[str, Any]) -> Path:# handles cache dir behavior
    try:
        from src.utils.paths import p  # project path helper
        base = p("data", "work", "transcripts", "_emb_cache")
    except Exception:
        base = Path("data/work/transcripts/_emb_cache")

    base.mkdir(parents=True, exist_ok=True)
    return base
def _cache_key(model_name: str, texts: List[str], namespace: str) -> str:# creates a stable cache key
    h = hashlib.sha1()
    h.update((namespace or "semantic").encode("utf-8"))
    h.update(b"\n")
    h.update((model_name or "").encode("utf-8"))
    h.update(b"\n")
    for t in texts:
        h.update(((t or "").strip()).encode("utf-8", errors="ignore"))
        h.update(b"\n")
    return h.hexdigest()
def _try_load_cached_embeddings(cache_path: Path) -> Optional[np.ndarray]:# loads cached data when it already exists
    try:
        if not cache_path.exists():
            return None
        data = np.load(str(cache_path), allow_pickle=False)
        return data["emb"].astype(np.float32)
    except Exception:
        return None
def _save_cached_embeddings(cache_path: Path, emb: np.ndarray) -> None:  # saves generated state or output files
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(str(cache_path), emb=emb.astype(np.float32))
    except Exception:
        pass
def _embed_matrix(# handles embed matrix behavior
    texts: List[str],
    model_name: str,
    device: str,
    batch_size: int,
    settings: Optional[Dict[str, Any]] = None,
    cache_tag: str = "default",
) -> np.ndarray:
    settings = settings or {}
    cfg = (settings or {}).get("semantic_highlights", {}) or {}

    cache_enabled = bool(cfg.get("cache_enabled", True))
    namespace = str(cfg.get("cache_namespace", "semantic_v1"))

    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    os.environ.setdefault("TRANSFORMERS_NO_FLAX", "1")

    cache_path: Optional[Path] = None
    if cache_enabled:
        cd = _cache_dir(settings)
        key = _cache_key(model_name, texts, f"{namespace}:{cache_tag}")
        cache_path = cd / f"{key}.npz"
        hit = _try_load_cached_embeddings(cache_path)
        if hit is not None and hit.shape[0] == len(texts):
            return hit

    # lazy import
    from sentence_transformers import SentenceTransformer  # creates sentence embeddings

    model = SentenceTransformer(model_name, device=device)
    embs = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    ).astype(np.float32)

    if cache_enabled and cache_path is not None:
        _save_cached_embeddings(cache_path, embs)

    return embs
def _mmr_select(# handles mmr select behavior
    candidates: List[dict],
    mat: np.ndarray,
    top_k: int,
    lambda_diversity: float,
    max_similarity: float = 0.86,
    max_temporal_overlap: float = 0.55,
    debug: bool = False,
) -> List[dict]:
    if not candidates:
        return []

    top_k = max(1, min(int(top_k), len(candidates)))
    lam = float(_clamp01(lambda_diversity))

    order = sorted(range(len(candidates)), key=lambda i: float(candidates[i]["score"]), reverse=True)
    selected = [order[0]]
    remaining = order[1:]

    while remaining and len(selected) < top_k:
        best, best_score = None, -1e18
        too_similar: List[int] = []
        for idx in remaining:
            base = float(candidates[idx]["score"])
            sim = max(float(mat[idx] @ mat[s]) for s in selected)
            temporal_overlap = max(_time_iou(candidates[idx], candidates[s]) for s in selected)
            if sim >= float(max_similarity) or temporal_overlap >= float(max_temporal_overlap):
                too_similar.append(idx)
                continue
            score = (1 - lam) * base - lam * sim
            if score > best_score:
                best, best_score = idx, score
        for idx in too_similar:
            if idx in remaining:
                if debug:
                    c = candidates[idx]
                    print(
                        f"[semantic-ai] REJECT {float(c['start']):.2f}-{float(c['end']):.2f}s "
                        f"score={float(c['score']):.3f} reason=too similar to selected clip"
                    )
                remaining.remove(idx)
        if best is None:
            break
        selected.append(best)
        remaining.remove(best)

    return [candidates[i] for i in selected]
def _word_count(text: str) -> int:# counts words in the given text
    return len(re.sub(r"\s+", " ", (text or "").strip()).split())
def _time_iou(a: dict, b: dict) -> float:# calculates overlap between two time ranges or boxes
    s1, e1 = float(a.get("start", 0.0)), float(a.get("end", 0.0))
    s2, e2 = float(b.get("start", 0.0)), float(b.get("end", 0.0))
    inter = max(0.0, min(e1, e2) - max(s1, s2))
    union = max(1e-6, max(e1, e2) - min(s1, s2))
    return float(inter / union)
def _clamp01(x: float) -> float:# limits a value so it stays inside the allowed range
    return max(0.0, min(1.0, float(x)))
