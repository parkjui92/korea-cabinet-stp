"""정권별 과기정책 의제 추이.

8년치(2018-09~2026-07)가 모이자 단일 시점으로는 안 보이던 것이 드러났다.
최근 1년만 보면 AI가 과기 의제 1위지만, 전 기간으로는 에너지·반도체가 앞선다.
정권 구간을 나눠 봐야 "무엇이 실제로 달라졌는가"를 말할 수 있다.

주의: 태그 사전은 최근 어휘로 만들어져 과거를 과소 계상할 수 있다. 그래서
핵심 주제는 태그와 별개로 **제목 원문 검색**을 병행해 교차 확인한다.
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.classify.agenda_role import ROLE_POLICY, role_of
from src.classify.relevance import classify

ROOT = Path(__file__).parent
ITEMS = ROOT / "data/export/agenda_items.jsonl"
OUT = ROOT / "data/export/era_trend.md"

# 정권 구간. 경계는 취임일 기준이며, 국무회의 개최일로 가른다.
ERAS = [
    ("문재인", "2018-09-04", "2022-05-09"),
    ("윤석열", "2022-05-10", "2025-05-31"),
    ("이재명", "2025-06-01", "2026-12-31"),
]

# 태그 사전을 우회한 교차 확인용. 정의가 흔들리지 않는 낱말만 쓴다.
CROSSCHECK = {
    "AI": re.compile(r"인공지능|AI(?![A-Za-z])|지능정보"),
    "반도체": re.compile(r"반도체"),
    "원자력": re.compile(r"원자력|원전"),
}


def era_of(date: str) -> str | None:
    for name, start, end in ERAS:
        if start <= date <= end:
            return name
    return None


def main() -> None:
    rows = [json.loads(line) for line in ITEMS.open(encoding="utf-8")]
    policy = [r for r in rows if role_of(r["category"], r["title"]) == ROLE_POLICY]

    totals: collections.Counter = collections.Counter()
    stc_counts: collections.Counter = collections.Counter()
    tag_counts: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    cross_counts: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)

    for row in policy:
        era = era_of(row["held_on"])
        if era is None:
            continue
        totals[era] += 1
        verdict = classify(row["title"], row.get("ministry_id"))
        if verdict.is_relevant:
            stc_counts[era] += 1
            for tag in verdict.tags:
                tag_counts[era][tag] += 1
        for label, pattern in CROSSCHECK.items():
            if pattern.search(row["title"]):
                cross_counts[era][label] += 1

    names = [name for name, _, _ in ERAS]
    lines = [
        "# 정권별 과학기술정책 의제 추이",
        "",
        f"대상: 정책안건 {sum(totals.values()):,}건 "
        "(법률공포·조직직제·인사 제외 — `ministry_share.md` 참고)",
        "",
        "## 과기정책 안건 비중",
        "",
        "| 정권 | 정책안건 | 과기정책 관련 | 비중 |",
        "|---|---:|---:|---:|",
    ]
    for name in names:
        total = totals[name]
        stc = stc_counts[name]
        share = f"{stc / total * 100:.1f}%" if total else "-"
        lines.append(f"| {name} | {total:,} | {stc:,} | {share} |")

    lines += [
        "",
        "재임 기간이 서로 다르므로 **건수가 아니라 비중**으로 읽어야 한다.",
        "",
        "## 주제별 안건 수",
        "",
        "| 주제 | " + " | ".join(names) + " |",
        "|---|" + "---:|" * len(names),
    ]
    all_tags = sorted(
        {t for c in tag_counts.values() for t in c},
        key=lambda t: -sum(tag_counts[n][t] for n in names),
    )
    for tag in all_tags:
        lines.append(
            f"| {tag} | " + " | ".join(str(tag_counts[n][tag]) for n in names) + " |"
        )

    lines += [
        "",
        "## 교차 확인 — 태그 사전을 우회한 제목 원문 검색",
        "",
        "태그 사전은 최근 어휘로 만들어져 과거를 과소 계상할 수 있다. 정의가 "
        "흔들리지 않는 낱말로 원문을 직접 세어 위 표의 추세가 사전 편향인지 "
        "실제 변화인지 가린다.",
        "",
        "| 검색어 | " + " | ".join(names) + " |",
        "|---|" + "---:|" * len(names),
    ]
    for label in CROSSCHECK:
        lines.append(
            f"| {label} | " + " | ".join(str(cross_counts[n][label]) for n in names) + " |"
        )

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"정권별 추이 -> {OUT}")
    for name in names:
        total = totals[name]
        share = f"{stc_counts[name] / total * 100:.1f}%" if total else "-"
        print(f"  {name}: 정책안건 {total:,}건, 과기 {stc_counts[name]:,}건 ({share})")


if __name__ == "__main__":
    main()
