"""Phase 3-B(경량): 의사일정의 부처보고·집중토의·협조사항 → 등판 데이터셋.

핵심 가치: **의결되지 않는 의제가 여기서만 잡힌다.** 「2026년 하반기 경제성장전략」
보고는 표결 없는 보고 안건이라 AgendaItem(의안 표)에는 없다. 영상 자막 없이도
"어느 부처가 언제 무엇을 들고 등판했는지"를 셀 수 있다 — 이미 받은 의사일정
첨부 안에 있던 데이터라 추가 수집 비용이 0이다.

발언 레이어(모두말씀)와 마찬가지로 이미 수집된 첨부를 재파싱만 한다.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.collect.agenda_doc import (
    KNOWN_CATEGORIES,
    parse_report_items,
    parse_with_kordoc,
)
from src.normalize.ministries import resolve, validate_against_observed
from src.normalize.textnorm import collapse, despace

ROOT = Path(__file__).parent
MANIFEST = ROOT / "data/export/attachment_manifest.jsonl"
OUT = ROOT / "data/export/report_items.jsonl"
REPORT = ROOT / "data/export/report_parse_report.json"
KORDOC = str(Path.home() / "node_modules/.bin/kordoc")

_SECTION_RE = re.compile(r"^[○※]\s*(.+?)\s*[:：]\s*(\d+)\s*건")


def declared_section_counts(doc: dict) -> dict[str, int]:
    """문서에 적힌 섹션별 선언 건수. `parse_report_items`의 판정 로직을 그대로 따른다."""
    counts: dict[str, int] = {}
    for block in doc["blocks"]:
        if block["type"] == "table":
            continue
        raw = collapse(block.get("text", ""))
        packed = re.sub(r"\s+", "", raw)
        if "차관회의" in packed or "즉석안건" in packed:
            continue
        m = _SECTION_RE.match(despace(raw))
        if not m:
            continue
        section = re.sub(r"\s+", "", m.group(1))
        if section in KNOWN_CATEGORIES or section == "일반안":
            continue
        counts[section] = counts.get(section, 0) + int(m.group(2))
    return counts


def main() -> None:
    records = [json.loads(line) for line in MANIFEST.open(encoding="utf-8")]
    by_meeting: dict[str, dict] = {}
    for r in records:
        if r["kind"] == "의사일정":
            by_meeting.setdefault(r["meeting_key"], r)

    print(f"의사일정 {len(by_meeting)}건에서 보고·토의 항목 파싱 시작\n")

    rows: list[dict] = []
    mismatches: list[dict] = []
    failures: list[dict] = []
    observed: list[tuple[str, str]] = []

    for i, (meeting_key, rec) in enumerate(sorted(by_meeting.items()), 1):
        path = ROOT / rec["path"]
        if not path.exists():
            failures.append({"meeting": meeting_key, "reason": "파일 없음"})
            continue

        try:
            doc = parse_with_kordoc(path, kordoc=KORDOC)
        except Exception as exc:  # noqa: BLE001
            failures.append({"meeting": meeting_key, "reason": f"{type(exc).__name__}: {exc}"})
            print(f"[{i:>3}] {meeting_key} kordoc 실패")
            continue

        items = parse_report_items(doc)
        declared = declared_section_counts(doc)
        actual: dict[str, int] = {}
        for item in items:
            actual[item.section] = actual.get(item.section, 0) + 1

        if declared and declared != actual:
            mismatches.append({"meeting": meeting_key, "declared": declared, "actual": actual})

        for item in items:
            row = asdict(item)
            row["meeting_key"] = meeting_key
            row["year"] = rec["year"]
            row["session"] = rec["session"]
            row["held_on"] = rec["date"]
            row["ministry_id"] = resolve(item.ministry_raw, rec["date"])
            rows.append(row)
            observed.append((item.ministry_raw, rec["date"]))

        flag = " ★불일치" if declared and declared != actual else ""
        print(f"[{i:>3}] {meeting_key} 보고·토의 {len(items):>2}건 {actual}{flag}")

    with OUT.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    ministry_problems = validate_against_observed(observed)
    unresolved = sorted(
        {r["ministry_raw"] for r in rows if not r["ministry_id"]}
    )

    report = {
        "meetings_parsed": len(by_meeting) - len(failures),
        "items_total": len(rows),
        "count_mismatches": mismatches,
        "failures": failures,
        "ministry_problems": ministry_problems[:50],
        "unresolved_ministries": unresolved,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"보고·토의 항목 {len(rows)}건 -> {OUT}")
    print(f"건수 불일치: {len(mismatches)}건")
    print(f"파싱 실패: {len(failures)}건")
    print(f"부처 시점 문제: {len(ministry_problems)}건")
    print(f"미등록/미해결 소관 표기: {unresolved or '없음'}")
    print(f"상세 리포트: {REPORT}")


if __name__ == "__main__":
    main()
