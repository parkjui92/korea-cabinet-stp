"""Phase 1 스텝 2: 브리핑 상세 + 첨부 수집.

멈췄다 다시 돌려도 안전하다. 상세 HTML과 첨부 파일 모두 이미 있으면 건너뛴다.
정부 사이트는 연속 요청에 연결을 끊으므로 Fetcher가 지연·재시도를 맡는다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.collect.briefing_view import parse_attachments, pick_wanted, extract_body
from src.collect.http import Fetcher
from src.normalize.meeting_key import parse_doc_type, parse_key

ROOT = Path(__file__).parent
INDEX = ROOT / "data/export/briefing_index.jsonl"
VIEW_DIR = ROOT / "data/raw/briefing_view"
ATT_DIR = ROOT / "data/raw/attachments"
BODY_DIR = ROOT / "data/raw/briefing_body"
MANIFEST = ROOT / "data/export/attachment_manifest.jsonl"


def main() -> None:
    rows = [json.loads(line) for line in INDEX.open(encoding="utf-8")]
    print(f"브리핑 {len(rows)}건 처리 시작\n")

    for d in (VIEW_DIR, ATT_DIR, BODY_DIR, MANIFEST.parent):
        d.mkdir(parents=True, exist_ok=True)

    fetcher = Fetcher(snapshot_dir=VIEW_DIR, delay=1.5)
    manifest: list[dict] = []
    downloaded = skipped = failed = 0

    for i, row in enumerate(rows, 1):
        key = parse_key(row["title"], row["date"])
        doc_type = parse_doc_type(row["title"])
        slug = f"{key.year}-{key.session:03d}" if key else f"unknown-{row['news_id']}"

        try:
            html = fetcher.get(
                "https://www.korea.kr/briefing/stateCouncilView.do",
                params={"newsId": row["news_id"]},
                cache_key=f"view_{row['news_id']}",
            )
        except RuntimeError as exc:
            print(f"[{i:>3}/{len(rows)}] {slug} 상세 실패: {exc}")
            failed += 1
            continue

        body = extract_body(html)
        (BODY_DIR / f"{slug}_{doc_type}_{row['news_id']}.txt").write_text(
            body, encoding="utf-8"
        )

        attachments = parse_attachments(html)
        wanted = pick_wanted(attachments)

        for att in wanted:
            dest = ATT_DIR / f"{slug}_{doc_type}_{att.kind}.{att.ext}"
            record = {
                "meeting_key": slug,
                "year": key.year if key else None,
                "session": key.session if key else None,
                "doc_type": doc_type,
                "news_id": row["news_id"],
                "date": row["date"],
                "kind": att.kind,
                "filename": att.filename,
                "file_id": att.file_id,
                "path": str(dest.relative_to(ROOT)),
            }

            if dest.exists() and dest.stat().st_size > 0:
                skipped += 1
                manifest.append(record)
                continue

            try:
                dest.write_bytes(fetcher.get_bytes(att.url))
                downloaded += 1
                manifest.append(record)
            except Exception as exc:  # noqa: BLE001 — 한 건 실패로 전체를 멈추지 않는다
                print(f"      ! {att.kind} 실패: {type(exc).__name__} {exc}")
                failed += 1

        print(
            f"[{i:>3}/{len(rows)}] {slug} {doc_type:6s} "
            f"첨부 {len(attachments)}건 중 {len(wanted)}건 대상 "
            f"({', '.join(a.kind for a in wanted) or '없음'})"
        )

    with MANIFEST.open("w", encoding="utf-8") as f:
        for record in manifest:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(
        f"\n완료 — 신규 {downloaded}건, 기존 {skipped}건, 실패 {failed}건"
        f"\n매니페스트: {MANIFEST}"
    )


if __name__ == "__main__":
    main()
