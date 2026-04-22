#!/usr/bin/env python3
"""Build a concrete voice-pack plus fallback voice-profile from article samples.

The builder is intentionally deterministic and offline-friendly so it can run
inside OpenClaw workspaces without additional model calls.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List, Sequence, Tuple


GENERIC_AVOID_PHRASES = [
    "随着AI的发展",
    "随着……的发展",
    "总而言之",
    "综上所述",
    "值得注意的是",
    "具体来说",
    "换言之",
    "我们不难发现",
    "由此可见",
    "毫无疑问",
    "未来已来",
    "底层逻辑",
    "认知升级",
]

TURN_MARKERS = [
    "问题到这里才刚开始",
    "再往下看一层",
    "但",
    "不过",
    "问题是",
    "说白了",
    "真正决定",
    "真正值得看",
]

EXPLANATION_MARKERS = [
    "你可以把它理解成",
    "换到普通读者的语境里",
    "举个更贴手的例子",
    "说白了",
    "换句话说",
]

JUDGMENT_MARKERS = [
    "我先把判断放前面",
    "真正",
    "值不值",
    "稀缺",
    "不是",
    "问题是",
    "说白了",
]

SIGNATURE_PHRASE_BLOCKLIST = [
    "问题到这里才刚开始",
    "再往下看一层",
    "值得注意的是",
    "值得一提的是",
    "具体来说",
    "具体而言",
    "换言之",
    "也就是说",
    "总之",
    "总而言之",
    "综上所述",
    "因为",
]

TITLE_RE = re.compile(r"^title:\s*(.+?)\s*$", re.IGNORECASE)
SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;]\s*")
FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)
HEADING_RE = re.compile(r"^\s*#+\s+")


def iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def strip_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub("", text, count=1)


def extract_title(path: Path, text: str) -> str:
    frontmatter_match = TITLE_RE.search(text)
    if frontmatter_match:
        return frontmatter_match.group(1).strip().strip('"').strip("'")

    for line in strip_frontmatter(text).splitlines():
        if HEADING_RE.match(line):
            return HEADING_RE.sub("", line).strip()
    return path.stem


def extract_paragraphs(text: str) -> List[str]:
    content = strip_frontmatter(text)
    paragraphs: List[str] = []
    current: List[str] = []
    in_code = False

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if not line.strip():
            if current:
                paragraph = " ".join(x.strip() for x in current).strip()
                if paragraph and not HEADING_RE.match(paragraph):
                    paragraphs.append(paragraph)
                current = []
            continue
        current.append(line)

    if current:
        paragraph = " ".join(x.strip() for x in current).strip()
        if paragraph and not HEADING_RE.match(paragraph):
            paragraphs.append(paragraph)

    return paragraphs


def split_sentences(text: str) -> List[str]:
    sentences = [x.strip() for x in SENTENCE_SPLIT_RE.split(text) if x.strip()]
    return [x for x in sentences if len(x) >= 6]


def dedupe_keep_order(items: Iterable[str], *, max_items: int) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        normalized = re.sub(r"\s+", " ", item).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= max_items:
            break
    return result


def exemplar_list(texts: Iterable[str], *, max_items: int) -> List[Dict[str, str]]:
    return [{"text": text} for text in dedupe_keep_order(texts, max_items=max_items)]


def mean_safe(values: Sequence[float], default: float) -> float:
    return round(mean(values), 2) if values else default


def detect_persona_mode(persona_text: str, article_text: str) -> str:
    merged = f"{persona_text}\n{article_text}"
    if any(marker in merged for marker in ["本虾", "作为一个 AI", "我是一个 AI", "我是 AI"]):
        return "ai_native"
    if "AI" in merged or "人工智能" in merged:
        return "mixed"
    return "human_like"


def detect_reader_relationship(persona_text: str) -> str:
    if any(token in persona_text for token in ["朋友", "聊天", "懂行的朋友"]):
        return "friend_to_friend"
    if any(token in persona_text for token in ["老师", "带你", "讲给你听"]):
        return "mentor_student"
    return "peer_to_peer"


def detect_opinion_strength(persona_text: str, article_text: str) -> str:
    merged = f"{persona_text}\n{article_text}"
    if any(token in merged for token in ["毒舌", "敢判断", "直接说", "没什么用", "重要得多"]):
        return "provocative"
    if any(token in merged for token in ["有立场", "判断", "说白了", "真正"]):
        return "clear_stance"
    return "mild_opinion"


def detect_humor_level(persona_text: str) -> str:
    if any(token in persona_text for token in ["毒舌", "调侃", "玩笑"]):
        return "light_humor"
    if any(token in persona_text for token in ["偶尔", "亲民", "接地气"]):
        return "occasional_wit"
    return "none"


def infer_boundary_notes(persona_text: str) -> str:
    notes = []
    if "不要写“随着AI的发展”" in persona_text or "不要写“随着" in persona_text:
        notes.append("Avoid generic report-style openings.")
    if "结尾必须落到具体代价、选择或下一步" in persona_text:
        notes.append("End on a concrete implication, cost, or choice.")
    if "不靠身份设定硬撑全篇" in persona_text:
        notes.append("Use persona to sharpen judgment, not to replace it.")
    return " ".join(notes) or "Stay specific, judgment-forward, and reader-aware."


def extract_avoid_phrases(persona_text: str) -> List[str]:
    detected = []
    for phrase in GENERIC_AVOID_PHRASES:
        if phrase in persona_text:
            detected.append(phrase)
    if "不是……而是……" in persona_text:
        detected.append("不是……而是……")
    return dedupe_keep_order(detected + GENERIC_AVOID_PHRASES, max_items=30)


def extract_signature_phrases(paragraphs: Sequence[str]) -> List[str]:
    prefixes: Counter[str] = Counter()
    for paragraph in paragraphs:
        for sentence in split_sentences(paragraph):
            prefix = sentence[:8].strip("，、：: ")
            if len(prefix) < 4:
                continue
            if any(sentence.startswith(blocked) or prefix.startswith(blocked[: len(prefix)]) for blocked in SIGNATURE_PHRASE_BLOCKLIST):
                continue
            prefixes[prefix] += 1
    selected = [phrase for phrase, count in prefixes.most_common(12) if count >= 1]
    return selected[:10]


def choose_turns(paragraphs: Sequence[str]) -> List[str]:
    selected = [p for p in paragraphs if any(marker in p for marker in TURN_MARKERS)]
    if not selected:
        selected = [p for p in paragraphs[1:-1] if len(p) <= 180]
    return dedupe_keep_order(selected, max_items=12)


def choose_explanation_moves(paragraphs: Sequence[str]) -> List[str]:
    selected = [p for p in paragraphs if any(marker in p for marker in EXPLANATION_MARKERS)]
    return dedupe_keep_order(selected, max_items=12)


def sentence_score(sentence: str) -> int:
    score = 0
    if 10 <= len(sentence) <= 80:
        score += 1
    if any(marker in sentence for marker in JUDGMENT_MARKERS):
        score += 2
    if "：" in sentence or "，" in sentence:
        score += 1
    return score


def choose_sharp_lines(paragraphs: Sequence[str]) -> List[str]:
    candidates: List[Tuple[int, str]] = []
    for paragraph in paragraphs:
        for sentence in split_sentences(paragraph):
            score = sentence_score(sentence)
            if score >= 2:
                candidates.append((score, sentence))
    ordered = [text for _, text in sorted(candidates, key=lambda item: (-item[0], len(item[1])))]
    return dedupe_keep_order(ordered, max_items=16)


def default_anti_examples(avoid_phrases: Sequence[str]) -> Dict[str, List[Dict[str, str]]]:
    openings = [
        {
            "text": "随着AI的发展，行业正在发生深刻变化。",
            "why_bad": "Generic topic announcement. No author presence, no stakes, no scene.",
        },
        {
            "text": "今天我们来聊聊这个热门话题。",
            "why_bad": "Low-information setup. Could open almost anything.",
        },
    ]
    transitions = [
        {
            "text": "值得注意的是，这说明了问题的复杂性。",
            "why_bad": "Template connector standing in for actual reasoning.",
        },
        {
            "text": "具体来说，这带来了很多深远影响。",
            "why_bad": "Abstract summary move with no object, action, or cost.",
        },
    ]
    endings = [
        {
            "text": "未来已来，我们都要拥抱变化。",
            "why_bad": "Banner-like slogan. No concrete implication or choice.",
        },
        {
            "text": "总之，这件事值得我们持续关注。",
            "why_bad": "Interchangeable closing line. Could end any article in the category.",
        },
    ]

    if "不是……而是……" in avoid_phrases:
        transitions.append(
            {
                "text": "不是这个问题难，而是我们还没有真正理解它。",
                "why_bad": "Reusable rhetorical shell that quickly turns into visible patterning.",
            }
        )

    return {
        "openings": openings[:20],
        "transitions": transitions[:20],
        "endings": endings[:20],
    }


def build_voice_pack(article_paths: Sequence[Path], persona_paths: Sequence[Path]) -> Dict[str, object]:
    article_bodies = []
    article_titles = []
    paragraphs: List[str] = []
    sentence_lengths: List[int] = []
    paragraph_sentence_counts: List[int] = []

    for path in article_paths:
        text = load_text(path)
        article_titles.append(extract_title(path, text))
        article_bodies.append(strip_frontmatter(text))
        body_paragraphs = extract_paragraphs(text)
        paragraphs.extend(body_paragraphs)
        for paragraph in body_paragraphs:
            sentences = split_sentences(paragraph)
            if sentences:
                paragraph_sentence_counts.append(len(sentences))
                sentence_lengths.extend(len(sentence) for sentence in sentences)

    persona_text = "\n".join(load_text(path) for path in persona_paths) if persona_paths else ""
    article_text = "\n".join(article_bodies)
    openings = [extract_paragraphs(load_text(path))[0] for path in article_paths if extract_paragraphs(load_text(path))]
    endings = [extract_paragraphs(load_text(path))[-1] for path in article_paths if extract_paragraphs(load_text(path))]
    turns = choose_turns(paragraphs)
    sharp_lines = choose_sharp_lines(paragraphs)
    explanation_moves = choose_explanation_moves(paragraphs)
    avoid_phrases = extract_avoid_phrases(persona_text)
    signature_phrases = extract_signature_phrases(paragraphs)

    avg_sentence_chars = mean_safe(sentence_lengths, 22.0)
    short_sentence_ratio = round(sum(1 for value in sentence_lengths if value < 18) / len(sentence_lengths), 2) if sentence_lengths else 0.3
    long_sentence_ratio = round(sum(1 for value in sentence_lengths if value > 45) / len(sentence_lengths), 2) if sentence_lengths else 0.1
    variation_score = round((max(sentence_lengths) - min(sentence_lengths)) / max(max(sentence_lengths), 1), 2) if sentence_lengths else 0.5

    persona_mode = detect_persona_mode(persona_text, article_text)
    reader_relationship = detect_reader_relationship(persona_text)
    opinion_strength = detect_opinion_strength(persona_text, article_text)
    humor_level = detect_humor_level(persona_text)
    boundary_notes = infer_boundary_notes(persona_text)
    now = iso_now()

    voice_pack = {
        "meta": {
            "created_at": now,
            "updated_at": now,
            "article_count": len(article_paths),
            "version": "1.0",
            "source_titles": article_titles[:50],
            "notes": "Built from article samples plus workspace persona notes.",
        },
        "persona": {
            "persona_mode": persona_mode,
            "reader_relationship": reader_relationship,
            "opinion_strength": opinion_strength,
            "humor_level": humor_level,
            "author_label": "custom",
            "boundary_notes": boundary_notes,
        },
        "rhythm": {
            "avg_sentence_chars": avg_sentence_chars,
            "short_sentence_ratio": short_sentence_ratio,
            "long_sentence_ratio": long_sentence_ratio,
            "variation_score": variation_score,
        },
        "openings": exemplar_list(openings, max_items=12),
        "turns": exemplar_list(turns, max_items=12),
        "endings": exemplar_list(endings, max_items=12),
        "sharp_lines": exemplar_list(sharp_lines, max_items=16),
        "explanation_moves": exemplar_list(explanation_moves, max_items=12),
        "signature_phrases": signature_phrases[:12],
        "avoid_phrases": avoid_phrases,
        "anti_examples": default_anti_examples(avoid_phrases),
        "prompt_injection": (
            "Write like a specific person is thinking live on the page. "
            "Land the judgment early. "
            f"Persona mode: {persona_mode}. "
            "Advance through cause, conflict, scene, implication, or cost, not stock connector phrases."
        ),
    }
    return voice_pack


def build_voice_profile(voice_pack: Dict[str, object], paragraph_sentence_counts: Sequence[int]) -> Dict[str, object]:
    persona = dict(voice_pack["persona"])  # type: ignore[index]
    rhythm = dict(voice_pack["rhythm"])  # type: ignore[index]
    meta = dict(voice_pack["meta"])  # type: ignore[index]

    profile = {
        "meta": {
            "created_at": meta["created_at"],
            "updated_at": meta["updated_at"],
            "article_count": meta["article_count"],
            "version": meta["version"],
            "sample_titles": meta.get("source_titles", [])[:10],
        },
        "persona": persona,
        "rhythm": {
            "avg_sentence_chars": rhythm["avg_sentence_chars"],
            "avg_paragraph_sentences": mean_safe(paragraph_sentence_counts, 2.0),
            "short_sentence_ratio": rhythm["short_sentence_ratio"],
            "long_sentence_ratio": rhythm["long_sentence_ratio"],
            "variation_score": rhythm["variation_score"],
        },
        "structure": {
            "preferred_section_count": 5,
            "uses_subheadings": False,
            "uses_numbered_lists": True,
            "uses_bullet_lists": False,
            "uses_summary_box": False,
            "opening_style": "bold_claim",
            "closing_style": "open_question",
            "avg_word_count": 1800,
        },
        "rhetoric": {
            "dominant_devices": ["contrast", "data_cite", "rhetorical_question"],
            "uses_technical_deep_dives": False,
            "simplification_style": "compare_to_known",
            "self_reference_frequency": "occasional" if persona["persona_mode"] != "human_like" else "rare",
        },
        "vocabulary": {
            "formality_level": "semi_formal",
            "english_loanword_style": "parenthetical",
            "signature_phrases": list(voice_pack.get("signature_phrases", []))[:20],
            "avoid_phrases": list(voice_pack.get("avoid_phrases", []))[:20],
            "domain_focus": ["general"],
        },
        "punctuation": {
            "prefers_chinese_comma": False,
            "uses_em_dash": False,
            "uses_ellipsis": False,
            "book_title_marks": True,
            "emoji_usage": "none",
            "emoji_style": [],
        },
        "tone": {
            "primary_tone": "conversational",
            "secondary_tone": "neutral_informative",
            "reader_relationship": persona["reader_relationship"],
            "humor_level": persona["humor_level"],
            "opinion_strength": persona["opinion_strength"],
        },
        "writing_prompt_injection": voice_pack["prompt_injection"],
    }
    return profile


def write_json(path: Path, data: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build voice-pack and fallback voice-profile from markdown article samples.")
    parser.add_argument("--article", action="append", required=True, help="Markdown article sample. Repeat for multiple files.")
    parser.add_argument("--persona-file", action="append", default=[], help="Workspace persona / memory file. Repeat as needed.")
    parser.add_argument("--voice-pack-output", required=True, help="Output path for voice-pack.json")
    parser.add_argument("--voice-profile-output", required=True, help="Output path for fallback voice-profile.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    article_paths = [Path(path).expanduser().resolve() for path in args.article]
    persona_paths = [Path(path).expanduser().resolve() for path in args.persona_file]

    for path in article_paths + persona_paths:
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"input file not found: {path}")

    voice_pack = build_voice_pack(article_paths, persona_paths)
    paragraph_sentence_counts = []
    for path in article_paths:
        for paragraph in extract_paragraphs(load_text(path)):
            sentences = split_sentences(paragraph)
            if sentences:
                paragraph_sentence_counts.append(len(sentences))
    voice_profile = build_voice_profile(voice_pack, paragraph_sentence_counts)

    write_json(Path(args.voice_pack_output).expanduser().resolve(), voice_pack)
    write_json(Path(args.voice_profile_output).expanduser().resolve(), voice_profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
