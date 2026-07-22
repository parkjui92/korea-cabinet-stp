"""Phase 3-B(경량) 산출물: 부처별 국무회의 등판 — 의결 없이 보고·토의된 의제.

`ministry_share.md`는 **의결된** 안건(대통령령안 등)만 센다. 그런데 「2026년
하반기 경제성장전략」처럼 표결 없이 보고만 되는 의제가 있고, 이런 의제가
오히려 정책 우선순위를 더 잘 드러낸다 — 시행령 개정은 이미 결정된 사안의
사후 절차지만, 부처보고는 그 부처가 지금 무엇을 국정 의제로 들고 나왔는지를
보여준다.

의사일정 첨부에 이미 있던 데이터라 추가 수집 비용이 0이다.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.classify.relevance import classify
from src.normalize.ministries import canonical_name

ROOT = Path(__file__).parent
REPORTS = ROOT / "data/export/report_items.jsonl"
OUT = ROOT / "data/export/ministry_agenda_appearances.md"

SECTION_ORDER = ["부처보고", "집중토의", "협조사항"]


def main() -> None:
    rows = [json.loads(line) for line in REPORTS.open(encoding="utf-8")]
    dates = [r["held_on"] for r in rows if r.get("held_on")]
    start, end = min(dates), max(dates)

    by_ministry: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    stc_by_ministry: dict[str, list] = collections.defaultdict(list)

    for row in rows:
        key = row.get("ministry_id") or f"?{row['ministry_raw']}"
        by_ministry[key][row["section"]] += 1
        verdict = classify(row["title"], row.get("ministry_id"))
        if verdict.is_relevant:
            stc_by_ministry[key].append((row, verdict))

    totals = {k: sum(c.values()) for k, c in by_ministry.items()}
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)

    lines = [
        "# 부처별 국무회의 등판 — 의결 없는 보고·토의 의제",
        "",
        f"기간 {start} ~ {end} · 부처보고·집중토의·협조사항 {len(rows):,}건",
        "",
        "`ministry_share.md`는 의결된 안건(대통령령안 등)만 센다. 이 표는 "
        "**표결 없이 보고·토의된 의제**를 센다 — 시행령 개정이 아니라 그 부처가 "
        "지금 국정 의제로 들고 나온 것이 무엇인지를 보여준다. 의사일정 첨부에서 "
        "추가 수집 없이 뽑았다.",
        "",
        "| 소관 | 부처보고 | 집중토의 | 협조사항 | 합계 | 과기정책 관련 |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for key, total in ranked:
        name = key[1:] if key.startswith("?") else (canonical_name(key, end) or key)
        c = by_ministry[key]
        stc_count = len(stc_by_ministry.get(key, []))
        lines.append(
            f"| {name} | {c.get('부처보고', 0)} | {c.get('집중토의', 0)} "
            f"| {c.get('협조사항', 0)} | {total} | {stc_count} |"
        )

    lines += ["", "## 과기정책 관련 등판 — 회차·제목·근거", ""]
    for key, entries in sorted(
        stc_by_ministry.items(), key=lambda kv: len(kv[1]), reverse=True
    ):
        if not entries:
            continue
        name = key[1:] if key.startswith("?") else (canonical_name(key, end) or key)
        lines.append(f"### {name} ({len(entries)}건)")
        lines.append("")
        for row, verdict in entries:
            lines.append(
                f"- 제{row['session']}회({row['held_on']}) [{row['section']}] "
                f"「{row['title']}」 — {', '.join(verdict.tags) or verdict.reasons[0]}"
            )
        lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    total_stc = sum(len(v) for v in stc_by_ministry.values())
    print(f"등판 {len(rows):,}건 (부처 {len(by_ministry)}곳) — 과기정책 관련 {total_stc}건 -> {OUT}")
    print(f"상위 5: {[(canonical_name(k, end) or k, v) for k, v in ranked[:5]]}")


if __name__ == "__main__":
    main()
