"""Phase 1 스텝 3: 의사일정 첨부 → 안건 데이터셋.

각 의사일정 문서를 kordoc CLI로 구조화한 뒤 안건 표를 뽑아 하나의 JSONL로 쌓고,
그 과정에서 두 가지를 함께 점검한다.

  · 문서가 스스로 선언한 건수(`법률안 3건`)와 실제 추출 건수가 맞는지
  · 등장한 기관명이 부처 정규화 표와 시점상 어긋나지 않는지

둘 다 조용히 틀리면 이후 모든 비율이 그럴듯하게 어긋나므로 여기서 잡는다.

건수 불일치가 곧 파싱 실패는 아니다. 일부 의사일정은 머리표에 적힌 건수와
실제로 실린 의안 수가 다르다 — 안건이 철회됐는데 머리표를 안 고친 경우다.
독립 파서(hwp5html)로 교차 확인했고, 표에 실제 의안번호가 붙은 쪽이 사실이다.
그래서 **표를 따르되 불일치를 리포트에 남긴다.**
"""

from __future__ import annotations

import json
import re

import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.collect.agenda_doc import NON_RESOLVED_CATEGORIES, parse_agenda_items, parse_with_kordoc
from src.normalize.ministries import resolve, validate_against_observed
from src.normalize.textnorm import collapse, despace

ROOT = Path(__file__).parent
MANIFEST = ROOT / "data/export/attachment_manifest.jsonl"
OUT = ROOT / "data/export/agenda_items.jsonl"
REPORT = ROOT / "data/export/agenda_parse_report.json"
KORDOC = str(Path.home() / "node_modules/.bin/kordoc")

# 머리표의 `법 률 안 : 3건` — 문서가 스스로 밝힌 건수.
_DECLARED_RE = re.compile(r"(법률공포안|법률안|대통령령안|총리령안|일반안건|일반안|보고안건)\s*[(:：]?\s*(\d+)\s*건")


def run_kordoc(path: Path) -> dict:
    return parse_with_kordoc(path, kordoc=KORDOC)


def declared_counts(doc: dict) -> dict[str, int]:
    """문서 머리표에 적힌 유형별 건수."""
    counts: dict[str, int] = {}
    for block in doc["blocks"]:
        text = (
            " ".join(
                c["text"]
                for row in block["table"]["cells"]
                for c in row
            )
            if block["type"] == "table"
            else block.get("text", "")
        )
        for name, num in _DECLARED_RE.findall(despace(collapse(text))):
            key = "일반안건" if name == "일반안" else name
            counts.setdefault(key, int(num))
    return counts


def main() -> None:
    records = [json.loads(line) for line in MANIFEST.open(encoding="utf-8")]
    agenda_files = [r for r in records if r["kind"] == "의사일정"]
    # 같은 회의에 브리핑·결과브리핑이 각각 첨부를 달 수 있다. 회차당 하나만.
    by_meeting: dict[str, dict] = {}
    for r in agenda_files:
        by_meeting.setdefault(r["meeting_key"], r)

    print(f"의사일정 {len(by_meeting)}건 파싱 시작\n")

    items: list[dict] = []
    mismatches: list[dict] = []
    failures: list[dict] = []
    observed: list[tuple[str, str]] = []

    for i, (meeting_key, rec) in enumerate(sorted(by_meeting.items()), 1):
        path = ROOT / rec["path"]
        if not path.exists():
            failures.append({"meeting": meeting_key, "reason": "파일 없음"})
            continue

        try:
            doc = run_kordoc(path)
        except Exception as exc:  # noqa: BLE001
            failures.append({"meeting": meeting_key, "reason": f"{type(exc).__name__}: {exc}"})
            print(f"[{i:>3}] {meeting_key} kordoc 실패 — {exc}")
            continue

        parsed = parse_agenda_items(doc)
        if not parsed:
            failures.append({"meeting": meeting_key, "reason": "의안 없음"})
            print(f"[{i:>3}] {meeting_key} 의안을 못 찾음")
            continue

        declared = declared_counts(doc)
        actual: dict[str, int] = {}
        for item in parsed:
            actual[item.category] = actual.get(item.category, 0) + 1

        if declared and declared != actual:
            mismatches.append(
                {"meeting": meeting_key, "declared": declared, "actual": actual}
            )

        for item in parsed:
            row = asdict(item)
            row["meeting_key"] = meeting_key
            row["year"] = rec["year"]
            row["session"] = rec["session"]
            row["held_on"] = rec["date"]
            row["ministry_id"] = resolve(item.submitter, rec["date"])
            row["is_resolved_item"] = item.category not in NON_RESOLVED_CATEGORIES
            items.append(row)
            observed.append((item.submitter, rec["date"]))

        flag = " ★불일치" if declared and declared != actual else ""
        print(f"[{i:>3}] {meeting_key} 안건 {len(parsed):>2}건 {actual}{flag}")

    with OUT.open("w", encoding="utf-8") as f:
        for row in items:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    ministry_problems = validate_against_observed(observed)
    unresolved = sorted({r["submitter"] for r in items if not r["ministry_id"]})

    report = {
        "meetings_parsed": len(by_meeting) - len(failures),
        "items_total": len(items),
        "count_mismatches": mismatches,
        "failures": failures,
        "ministry_problems": ministry_problems[:50],
        "ministry_problem_total": len(ministry_problems),
        "unresolved_ministries": unresolved,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"안건 {len(items)}건 -> {OUT}")
    print(f"건수 불일치 회의: {len(mismatches)}건")
    print(f"파싱 실패: {len(failures)}건")
    print(f"부처 시점 문제: {len(ministry_problems)}건")
    print(f"미등록 기관명: {unresolved or '없음'}")
    print(f"상세 리포트: {REPORT}")


if __name__ == "__main__":
    main()
