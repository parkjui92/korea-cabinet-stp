"""Phase 3-A: 모두말씀 첨부 → 발언 데이터셋.

화자가 문서에 명시돼 있어 ASR 화자 추정이 필요 없다. 다만 표기 없이 이어지는
문단은 문서 성격상 대통령 발언이므로 `document_default`로 따로 표시한다.
발언 점유를 잴 때 두 등급을 섞으면 안 된다.
"""

from __future__ import annotations

import collections
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.collect.agenda_doc import parse_with_kordoc
from src.structure.remarks import parse_remarks

ROOT = Path(__file__).parent
MANIFEST = ROOT / "data/export/attachment_manifest.jsonl"
OUT = ROOT / "data/export/utterances.jsonl"
REPORT = ROOT / "data/export/remarks_parse_report.json"
KORDOC = str(Path.home() / "node_modules/.bin/kordoc")


def _backfill_ministry_by_name(rows: list[dict]) -> int:
    """부처가 안 적힌 장관 발언을, 같은 인물의 다른 발언으로 채운다.

    `- 안규백 장관 :`처럼 부처를 생략한 표기가 있는데, 같은 사람이 다른 회차에서
    `안규백 국방부 장관`으로 나온다. 코퍼스 안의 근거로 채우는 것이므로
    추측이 아니지만, 문서에 직접 적힌 것과는 구분되도록 표시해 둔다.
    """
    known: dict[str, str] = {}
    for row in rows:
        if row["speaker_name"] and row["ministry_id"] and len(row["speaker_name"]) >= 2:
            known.setdefault(row["speaker_name"], row["ministry_id"])

    filled = 0
    for row in rows:
        if row["speaker_type"] != "장관" or row["ministry_id"]:
            continue
        guess = known.get(row["speaker_name"])
        if guess:
            row["ministry_id"] = guess
            row["ministry_source"] = "corpus_backfill"
            filled += 1
    for row in rows:
        row.setdefault("ministry_source", "document" if row["ministry_id"] else "")
    return filled


def main() -> None:
    records = [json.loads(line) for line in MANIFEST.open(encoding="utf-8")]
    by_meeting: dict[str, dict] = {}
    for r in records:
        if r["kind"] == "모두말씀":
            by_meeting.setdefault(r["meeting_key"], r)

    print(f"모두말씀 {len(by_meeting)}건 파싱 시작\n")

    rows: list[dict] = []
    failures: list[dict] = []
    unresolved_speakers: collections.Counter = collections.Counter()

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

        utterances = parse_remarks(doc, when=rec["date"])
        explicit = sum(1 for u in utterances if u.attribution == "explicit")

        for u in utterances:
            row = asdict(u)
            row["meeting_key"] = meeting_key
            row["year"] = rec["year"]
            row["session"] = rec["session"]
            row["held_on"] = rec["date"]
            row["char_count"] = len(u.text)
            rows.append(row)
            if u.attribution == "explicit" and not u.is_president and not u.ministry_id:
                unresolved_speakers[u.speaker_raw] += 1

        print(f"[{i:>3}] {meeting_key} 발언 {len(utterances):>3}건 (화자표기 {explicit}건)")

    backfilled = _backfill_ministry_by_name(rows)

    with OUT.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    speakers = collections.Counter(
        r["speaker_raw"] for r in rows if r["attribution"] == "explicit"
    )
    report = {
        "meetings_parsed": len(by_meeting) - len(failures),
        "utterances_total": len(rows),
        "explicit_attribution": sum(1 for r in rows if r["attribution"] == "explicit"),
        "document_default": sum(1 for r in rows if r["attribution"] == "document_default"),
        "distinct_speakers": len(speakers),
        "top_speakers": speakers.most_common(30),
        "unresolved_speakers": unresolved_speakers.most_common(),
        "failures": failures,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"발언 {len(rows):,}건 -> {OUT}")
    print(f"  화자 명시 {report['explicit_attribution']:,}건 / 문서기본 {report['document_default']:,}건")
    print(f"  구분된 화자 {report['distinct_speakers']}명")
    print(f"  부처 미해결 화자: {len(unresolved_speakers)}종")
    print(f"파싱 실패: {len(failures)}건")


if __name__ == "__main__":
    main()
