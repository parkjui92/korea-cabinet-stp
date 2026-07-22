"""Phase 3-A 산출물: 대통령 과기정책 발언록.

모두말씀 문서는 대통령 모두발언이 대부분이다(1,107건 중 1,074건). 부처별 발언
점유를 재기엔 부족하지만, **대통령의 정책 발언·지시 코퍼스**로는 최상급이다.
정책 계보 추적(발언 → 지시 → 의결)의 앞단이 여기서 나온다.

같은 회차의 의결 안건과 붙여, 그날 무슨 말이 오갔고 무엇이 의결됐는지를
한자리에서 볼 수 있게 한다.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.classify.agenda_role import ROLE_POLICY, role_of
from src.classify.relevance import CORE, classify
from src.normalize.ministries import canonical_name

ROOT = Path(__file__).parent
UTT = ROOT / "data/export/utterances.jsonl"
ITEMS = ROOT / "data/export/agenda_items.jsonl"
OUT = ROOT / "data/export/president_stc_remarks.md"

# 지시성 발언을 가려내는 표지. 국무회의 모두발언의 관용 표현이다.
DIRECTIVE_MARKERS = (
    "주시기 바랍니다",
    "주기 바랍니다",
    "해 주십시오",
    "당부드립니다",
    "당부합니다",
    "지시합니다",
    "검토해",
    "마련해",
    "추진해",
    "점검해",
)


def is_directive(text: str) -> bool:
    return any(m in text for m in DIRECTIVE_MARKERS)


def main() -> None:
    utterances = [json.loads(line) for line in UTT.open(encoding="utf-8")]
    items = [json.loads(line) for line in ITEMS.open(encoding="utf-8")]

    scored = []
    for u in utterances:
        verdict = classify(u["text"], u.get("ministry_id"))
        if verdict.is_relevant:
            scored.append((u, verdict))

    agenda_by_meeting = collections.defaultdict(list)
    for row in items:
        if role_of(row["category"], row["title"]) != ROLE_POLICY:
            continue
        if classify(row["title"], row.get("ministry_id")).is_relevant:
            agenda_by_meeting[row["meeting_key"]].append(row)

    tag_counts = collections.Counter(t for _, v in scored for t in v.tags)
    directives = [(u, v) for u, v in scored if is_directive(u["text"])]

    lines = [
        "# 대통령 과학기술정책 발언록",
        "",
        f"모두말씀 {len({u['meeting_key'] for u in utterances})}개 회차 · 전체 발언 "
        f"{len(utterances):,}건 중 과기정책 관련 **{len(scored):,}건** "
        f"(그중 지시성 {len(directives):,}건)",
        "",
        "> 출처: 대한민국 정책브리핑 국무회의 브리핑 첨부 「모두말씀」 "
        "(공공누리 제1유형). 화자는 문서에 표기된 것을 그대로 쓴다.",
        "",
        "## 주제별 발언 빈도",
        "",
        "| 주제 | 발언 수 |",
        "|---|---:|",
    ]
    for tag, count in tag_counts.most_common():
        lines.append(f"| {tag} | {count} |")

    lines += ["", "## 회차별 — 발언과 그날의 의결", ""]

    by_meeting = collections.defaultdict(list)
    for u, v in scored:
        by_meeting[(u["year"], u["session"], u["held_on"], u["meeting_key"])].append((u, v))

    for (year, session, held, key), entries in sorted(by_meeting.items(), reverse=True):
        lines.append(f"### {year}년 제{session}회 ({held})")
        lines.append("")
        for u, v in entries:
            mark = "**[지시]** " if is_directive(u["text"]) else ""
            who = u["speaker_raw"]
            tags = ", ".join(v.tags) or "-"
            text = u["text"]
            if len(text) > 420:
                text = text[:420] + "…"
            lines.append(f"- {mark}`{who}` ({tags})")
            lines.append(f"  > {text}")
        related = agenda_by_meeting.get(key, [])
        if related:
            lines.append("")
            lines.append(f"  **같은 날 의결된 과기 안건 {len(related)}건**")
            for row in related:
                ministry = canonical_name(row["ministry_id"], held) or row["submitter"]
                lines.append(
                    f"  - {row['category']} 제{row['bill_no']}호 「{row['title']}」 ({ministry})"
                )
        lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"과기정책 발언 {len(scored):,}건 (지시성 {len(directives):,}건) -> {OUT}")
    print(f"주제 분포: {dict(tag_counts.most_common(8))}")


if __name__ == "__main__":
    main()
