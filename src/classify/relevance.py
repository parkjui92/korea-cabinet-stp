"""과학기술정책 관련성 판정.

판정은 늘 **근거와 함께** 나온다. 어떤 축(소관부처/주제태그)에서 어느 키워드로
걸렸는지를 같이 저장해야, 나중에 "이 안건이 왜 과기정책으로 잡혔나"를 되짚고
분류기를 고칠 수 있다. 근거 없는 라벨은 검증이 불가능해 연구에 못 쓴다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from ..normalize.ministries import _load as _load_ministries  # noqa: PLC2701

TAXONOMY_PATH = Path(__file__).parent / "taxonomy.yaml"

CORE = "핵심"
ADJACENT = "연관"
UNRELATED = "무관"

# 짧은 라틴 약어는 단어 경계를 요구한다. `AI`가 `TRAIN`에 걸리면 안 된다.
_SHORT_LATIN = re.compile(r"^[A-Za-z0-9&]{1,4}$")


@dataclass
class Verdict:
    level: str
    tags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def is_relevant(self) -> bool:
        return self.level in (CORE, ADJACENT)


@lru_cache(maxsize=1)
def _taxonomy() -> dict:
    return yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))


def _matches(keyword: str, text: str, normalized: str) -> bool:
    """키워드가 텍스트에 있는지.

    한글은 붙여쓰기 변형이 많아(`데이터 센터`/`데이터센터`) 공백을 지운 사본에도
    맞춰 본다. 반면 짧은 라틴 약어는 단어 경계를 지켜야 오탐이 없다.
    """
    if _SHORT_LATIN.match(keyword):
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])", text) is not None
    return keyword in text or keyword.replace(" ", "") in normalized


def match_tags(text: str) -> tuple[list[str], list[str], list[str]]:
    """(태그, strong 적중 근거, any 적중 근거)."""
    normalized = re.sub(r"\s+", "", text or "")
    tags: list[str] = []
    strong_hits: list[str] = []
    any_hits: list[str] = []

    for tag, spec in _taxonomy()["tags"].items():
        hit_strong = [k for k in (spec.get("strong") or []) if _matches(k, text, normalized)]
        hit_any = [k for k in (spec.get("any") or []) if _matches(k, text, normalized)]
        if hit_strong or hit_any:
            tags.append(tag)
        strong_hits += [f"{tag}:{k}" for k in hit_strong]
        any_hits += [f"{tag}:{k}" for k in hit_any]

    return tags, strong_hits, any_hits


def classify(text: str, ministry_id: str | None = None) -> Verdict:
    """안건명·발언 등 한 덩어리의 텍스트를 판정한다.

    핵심 — 소관이 과기 핵심부처이거나, strong 태그가 걸렸을 때
    연관 — 소관이 인접부처이면서 태그가 걸렸을 때 (예: 기재부의 R&D 예산)
    무관 — 그 외
    """
    data = _load_ministries()
    core_ids = set(data["science_tech_core"])
    adjacent_ids = set(data["science_tech_adjacent"])

    tags, strong_hits, any_hits = match_tags(text)
    reasons: list[str] = []

    ministry_is_core = ministry_id in core_ids if ministry_id else False
    ministry_is_adjacent = ministry_id in adjacent_ids if ministry_id else False

    if ministry_is_core:
        reasons.append(f"소관부처(핵심)={ministry_id}")
    if strong_hits:
        reasons.append("강태그=" + ",".join(strong_hits[:5]))

    if ministry_is_core or strong_hits:
        return Verdict(level=CORE, tags=tags, reasons=reasons)

    if ministry_is_adjacent and (tags or any_hits):
        reasons.append(f"소관부처(인접)={ministry_id}")
        if any_hits:
            reasons.append("약태그=" + ",".join(any_hits[:5]))
        return Verdict(level=ADJACENT, tags=tags, reasons=reasons)

    return Verdict(level=UNRELATED, tags=tags, reasons=[])
