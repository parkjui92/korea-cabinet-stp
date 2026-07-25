"""Phase 4 스텝 1: 정적 사이트가 소비할 데이터 번들 생성.

분류(과기정책 판정·역할 구분)는 **여기서 미리 계산해 굽는다.** 브라우저에서
다시 하지 않는다 — 태그 사전과 부처 계보가 파이썬 쪽에 있고, 그 로직이 이번
작업에서만 두 번 고쳐졌기 때문이다(부처 티어 조정, `전력` 동음이의어). 판정
기준이 두 곳에 흩어지면 조용히 어긋난다.

각 안건에는 원문 링크를 붙인다. 공공누리 제1유형은 출처 표시가 의무이고,
연구자가 인용하려면 어차피 원문에 닿아야 한다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.classify.agenda_role import role_of
from src.classify.relevance import CORE, Verdict, classify, match_tags
from src.normalize.ministries import _load as _load_ministries  # noqa: PLC2701
from src.normalize.ministries import canonical_name

ROOT = Path(__file__).parent
EXPORT = ROOT / "data/export"
OUT_DIR = ROOT / "site/data"

VIEW_URL = "https://www.korea.kr/briefing/stateCouncilView.do?newsId="


def load_jsonl(name: str) -> list[dict]:
    path = EXPORT / name
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def why_text(verdict: Verdict, title: str, ministry_id: str | None, when: str) -> str:
    """판정 근거를 사람이 읽는 문장으로.

    `Verdict.reasons`는 내부 진단용이라 `소관부처(인접)=kcc`,
    `약태그=디지털전환:정보통신`처럼 ID와 포맷이 날것으로 들어 있다. 연구자가
    "왜 이게 과기정책으로 잡혔나"를 확인하려면 부처명과 실제 걸린 낱말이
    보여야 한다.
    """
    if not verdict.is_relevant:
        return ""

    data = _load_ministries()
    parts: list[str] = []

    if ministry_id in set(data["science_tech_core"]):
        parts.append(f"소관 {canonical_name(ministry_id, when)}")
    elif ministry_id in set(data["science_tech_adjacent"]):
        parts.append(f"소관 {canonical_name(ministry_id, when)}(연관 부처)")

    # `AI:인공지능` → `인공지능`. 중복을 지우고 실제 걸린 낱말만 남긴다.
    _, strong_hits, any_hits = match_tags(title)
    words: list[str] = []
    for hit in strong_hits + any_hits:
        word = hit.split(":", 1)[-1]
        if word not in words:
            words.append(word)
    if words:
        parts.append("주제어 " + ", ".join(f"‘{w}’" for w in words[:4]))

    return " · ".join(parts)


def build_meetings() -> dict[str, dict]:
    """회의별 메타 + 원문 링크. 링크는 브리핑 문서의 newsId에서 온다."""
    manifest = load_jsonl("attachment_manifest.jsonl")
    meetings: dict[str, dict] = {}
    for rec in manifest:
        key = rec["meeting_key"]
        entry = meetings.setdefault(
            key,
            {
                "key": key,
                "year": rec["year"],
                "session": rec["session"],
                "date": rec["date"],
                "news_ids": {},
            },
        )
        # 같은 회의에 '브리핑'과 '결과브리핑'이 따로 올라온다. 둘 다 남긴다.
        entry["news_ids"][rec["doc_type"]] = rec["news_id"]
    return meetings


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    meetings = build_meetings()
    agenda = load_jsonl("agenda_items.jsonl")
    reports = load_jsonl("report_items.jsonl")
    utterances = load_jsonl("utterances.jsonl")

    # ── 안건 ────────────────────────────────────────────────────────
    agenda_out = []
    for row in agenda:
        verdict = classify(row["title"], row.get("ministry_id"))
        mid = row.get("ministry_id")
        agenda_out.append(
            {
                "billNo": row["bill_no"],
                "category": row["category"],
                "title": row["title"],
                "ministryId": mid,
                # 정규화가 안 된 표기(`관계부처` 등)는 원문을 그대로 보여준다.
                "ministry": canonical_name(mid, row["held_on"]) if mid else row["submitter"],
                "meetingKey": row["meeting_key"],
                "date": row["held_on"],
                "role": role_of(row["category"], row["title"]),
                "stc": verdict.level if verdict.is_relevant else None,
                "core": verdict.level == CORE,
                "tags": verdict.tags,
                "why": why_text(verdict, row["title"], mid, row["held_on"]),
                "cabinetResult": row.get("cabinet_result") or "",
            }
        )

    # ── 보고·토의 ───────────────────────────────────────────────────
    reports_out = []
    for row in reports:
        verdict = classify(row["title"], row.get("ministry_id"))
        mid = row.get("ministry_id")
        reports_out.append(
            {
                "section": row["section"],
                "title": row["title"],
                "ministryId": mid,
                "ministry": canonical_name(mid, row["held_on"]) if mid else row["ministry_raw"],
                "meetingKey": row["meeting_key"],
                "date": row["held_on"],
                "stc": verdict.level if verdict.is_relevant else None,
                "tags": verdict.tags,
            }
        )

    # ── 발언 (전체) ─────────────────────────────────────────────────
    # 교차 검색("이 낱말이 나온 발언 → 그 회의 → 그날 의결")이 성립하려면
    # 발언 전문이 검색 대상이어야 한다. 과기 관련만 담으면 "GPU"·"독자적"처럼
    # 태그엔 없지만 실제로 언급된 낱말을 못 찾는다. 4,603건 전부 넣되(gzip 후
    # 부담 없음), 과기 관련 여부는 stc 플래그로 표시한다.
    utterances_out = []
    for row in utterances:
        verdict = classify(row["text"], row.get("ministry_id"))
        utterances_out.append(
            {
                "speaker": row["speaker_raw"],
                "speakerType": row["speaker_type"],
                "ministryId": row.get("ministry_id"),
                "text": row["text"],
                "meetingKey": row["meeting_key"],
                "date": row["held_on"],
                "stc": verdict.is_relevant,
                "tags": verdict.tags,
            }
        )

    # ── 부처 사전 (화면 필터용) ─────────────────────────────────────
    ministries_data = _load_ministries()
    latest = max(r["held_on"] for r in agenda)
    ministries_out = {
        entry["id"]: {
            "name": canonical_name(entry["id"], latest),
            "category": entry.get("category", ""),
            "core": entry["id"] in ministries_data["science_tech_core"],
            "adjacent": entry["id"] in ministries_data["science_tech_adjacent"],
        }
        for entry in ministries_data["ministries"]
    }

    meetings_out = [
        {
            **m,
            "url": VIEW_URL + (m["news_ids"].get("브리핑") or next(iter(m["news_ids"].values()))),
        }
        for m in sorted(meetings.values(), key=lambda x: x["date"])
    ]

    bundle = {
        "meta": {
            "generatedFrom": "대한민국 정책브리핑 국무회의 브리핑 첨부 문서",
            "license": "공공누리 제1유형 (출처표시)",
            "sourceUrl": "https://www.korea.kr/briefing/stateCouncilList.do",
            "range": [min(r["held_on"] for r in agenda), latest],
            "meetings": len(meetings_out),
            "agendaTotal": len(agenda_out),
            "agendaStc": sum(1 for a in agenda_out if a["stc"]),
        },
        "ministries": ministries_out,
        "meetings": meetings_out,
        "agenda": agenda_out,
        "reports": reports_out,
        "utterances": utterances_out,
    }

    out = OUT_DIR / "bundle.json"
    out.write_text(json.dumps(bundle, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    size_mb = out.stat().st_size / 1024 / 1024
    print(f"번들 -> {out}  ({size_mb:.1f} MB)")
    print(f"  회의 {len(meetings_out)} · 안건 {len(agenda_out):,} "
          f"(과기 {bundle['meta']['agendaStc']:,}) · 보고토의 {len(reports_out)} "
          f"· 발언(과기) {len(utterances_out)}")


if __name__ == "__main__":
    main()
