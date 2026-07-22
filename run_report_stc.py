"""Phase 1 산출물: 과학기술정책 안건 목록과 부처별 의제 점유.

두 가지를 낸다.

  1. `stc_agenda.md`  — 인용 가능한 과기·산업 안건 목록. 각주 문안까지 붙여
     정책연구 본문에 그대로 옮길 수 있게 한다.
  2. `ministry_share.md` — 부처별 안건 점유 집계. 조직개편이 낀 부처는
     비교 불가 경고를 함께 찍는다. 경고 없이 시계열을 그리면 2025-10-01의
     기능 이관이 정책 변화처럼 보인다.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.classify.agenda_role import ROLE_POLICY, role_of
from src.classify.relevance import ADJACENT, CORE, classify
from src.normalize.ministries import canonical_name, comparability

ROOT = Path(__file__).parent
ITEMS = ROOT / "data/export/agenda_items.jsonl"
OUT_DIR = ROOT / "data/export"


def load() -> list[dict]:
    return [json.loads(line) for line in ITEMS.open(encoding="utf-8")]


def footnote(row: dict) -> str:
    """정책연구 본문에 그대로 넣을 수 있는 각주 문안."""
    held = row.get("held_on") or ""
    ministry = canonical_name(row["ministry_id"], held) if row["ministry_id"] else row["submitter"]
    return (
        f"「{row['title']}」, 제{row['session']}회 국무회의({held}) "
        f"{row['category']} 제{row['bill_no']}호, {ministry} 제출."
    )


def build_agenda_report(rows: list[dict]) -> str:
    scored = []
    for row in rows:
        verdict = classify(row["title"], row.get("ministry_id"))
        if verdict.is_relevant:
            scored.append((row, verdict))

    lines = [
        "# 과학기술정책 관련 국무회의 안건",
        "",
        f"전체 안건 {len(rows):,}건 중 과기정책 관련 **{len(scored):,}건**",
        "",
        "판정은 소관부처(1축)와 주제 태그(2축)를 함께 본다. 부처만 보면 "
        "기재부 소관 R&D 예산이나 국무조정실 소관 규제 안건을 놓친다.",
        "",
        "> 출처: 대한민국 정책브리핑 국무회의 브리핑 첨부 「의사일정」 "
        "(공공누리 제1유형). 각 회차 원문에서 직접 추출.",
        "",
    ]

    by_meeting = collections.defaultdict(list)
    for row, verdict in scored:
        by_meeting[(row["year"], row["session"], row.get("held_on"))].append((row, verdict))

    for (year, session, held), entries in sorted(by_meeting.items(), reverse=True):
        lines.append(f"## {year}년 제{session}회 국무회의 ({held})")
        lines.append("")
        lines.append("| 의안번호 | 유형 | 안건명 | 소관 | 판정 | 태그 |")
        lines.append("|---|---|---|---|---|---|")
        for row, verdict in entries:
            ministry = (
                canonical_name(row["ministry_id"], held)
                if row["ministry_id"]
                else row["submitter"]
            )
            mark = "**핵심**" if verdict.level == CORE else "연관"
            lines.append(
                f"| {row['bill_no']} | {row['category']} | {row['title']} "
                f"| {ministry} | {mark} | {', '.join(verdict.tags) or '-'} |"
            )
        lines.append("")
        lines.append("<details><summary>각주 문안</summary>")
        lines.append("")
        for row, _ in entries:
            lines.append(f"- {footnote(row)}")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    return "\n".join(lines)


def build_share_report(rows: list[dict]) -> str:
    dates = [r["held_on"] for r in rows if r.get("held_on")]
    if not dates:
        return "# 부처별 의제 점유\n\n데이터 없음\n"
    start, end = min(dates), max(dates)

    by_role = collections.Counter(role_of(r["category"], r["title"]) for r in rows)
    policy_rows = [r for r in rows if role_of(r["category"], r["title"]) == ROLE_POLICY]

    lines = [
        "# 부처별 국무회의 의제 점유",
        "",
        f"기간 {start} ~ {end} · 전체 안건 {len(rows):,}건",
        "",
        "## 왜 전체 안건으로 세지 않는가",
        "",
        "제출기관을 그대로 세면 점유율이 크게 왜곡된다. 실측에서 법제처가 "
        f"{sum(1 for r in rows if r.get('ministry_id') == 'moleg'):,}건으로 1위였는데, "
        "그중 대부분이 **법률공포안**이다. 국회를 통과한 법률을 공포하는 절차이지 "
        "법제처의 정책 발의가 아니다. 행정안전부의 상당수도 타 부처 **직제 개정령**"
        "으로, 정부조직 관리자로서 대신 올리는 것이다.",
        "",
        "| 역할 | 건수 | 비중 |",
        "|---|---:|---:|",
    ]
    for role, count in by_role.most_common():
        lines.append(f"| {role} | {count:,} | {count / len(rows) * 100:.1f}% |")

    lines += [
        "",
        f"아래 점유율은 **정책안건 {len(policy_rows):,}건**을 분모로 한다. "
        "형식적 통로를 뺀 실질 의제 기준이다.",
        "",
        "## 정책안건 기준 부처별 점유",
        "",
        "| 소관부처 | 정책안건 | 점유율 | 과기정책 관련 | 비교 주의 |",
        "|---|---:|---:|---:|---|",
    ]

    total = collections.Counter()
    stc = collections.Counter()
    for row in policy_rows:
        mid = row.get("ministry_id") or f"?{row['submitter']}"
        total[mid] += 1
        if classify(row["title"], row.get("ministry_id")).is_relevant:
            stc[mid] += 1

    grand = sum(total.values())
    for mid, count in total.most_common():
        name = canonical_name(mid, end) or mid
        warn = ""
        if not mid.startswith("?"):
            result = comparability(mid, start, end)
            if not result.comparable:
                warn = f"★ {result.warning}"
        lines.append(
            f"| {name} | {count} | {count / grand * 100:.1f}% "
            f"| {stc.get(mid, 0)} | {warn} |"
        )

    lines += [
        "",
        "**★ 표시 부처는 이 기간에 조직개편이 있었다.** 개편 전후를 그냥 이어 "
        "시계열로 그리면 기능 이관이 정책 변화처럼 보인다. 특히 산업통상자원부"
        "→산업통상부는 개명처럼 보이지만 에너지 기능이 기후에너지환경부로 "
        "넘어갔다(2025-10-01).",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    rows = load()
    print(f"안건 {len(rows):,}건 로드")

    agenda = OUT_DIR / "stc_agenda.md"
    agenda.write_text(build_agenda_report(rows), encoding="utf-8")
    print(f"과기정책 안건 목록 -> {agenda}")

    share = OUT_DIR / "ministry_share.md"
    share.write_text(build_share_report(rows), encoding="utf-8")
    print(f"부처별 의제 점유   -> {share}")


if __name__ == "__main__":
    main()
