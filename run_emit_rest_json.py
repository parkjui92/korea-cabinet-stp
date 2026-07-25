"""파싱·분류 결과를 PostgREST 대량삽입용 JSON으로 변환한다.

컬럼명을 테이블과 정확히 일치(snake_case)시켜, Bash가 curl로 그대로 POST할 수
있게 한다. 대용량 표는 청크로 나눠 페이로드·타임아웃을 피한다.
분류(부처·태그·역할)는 파이썬 계산값 그대로.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.classify.agenda_role import role_of
from src.classify.relevance import classify
from src.normalize.ministries import _load as _load_ministries  # noqa: PLC2701
from src.normalize.ministries import canonical_name

ROOT = Path(__file__).parent
EXPORT = ROOT / "data/export"
OUT = ROOT / "data/rest"
CHUNK = 2000
VIEW_URL = "https://www.korea.kr/briefing/stateCouncilView.do?newsId="


def load_jsonl(name: str) -> list[dict]:
    return [json.loads(line) for line in (EXPORT / name).open(encoding="utf-8")]


def none_if_blank(v):
    return v if v not in ("", None) else None


def dump_chunks(table: str, rows: list[dict]) -> int:
    for i in range(0, len(rows), CHUNK):
        part = i // CHUNK
        (OUT / f"{table}.{part:03d}.json").write_text(
            json.dumps(rows[i : i + CHUNK], ensure_ascii=False), encoding="utf-8"
        )
    return -(-len(rows) // CHUNK)  # ceil


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()

    data = _load_ministries()
    core, adjacent = set(data["science_tech_core"]), set(data["science_tech_adjacent"])
    agenda = load_jsonl("agenda_items.jsonl")
    utterances = load_jsonl("utterances.jsonl")
    reports = load_jsonl("report_items.jsonl")
    manifest = load_jsonl("attachment_manifest.jsonl")
    latest = max(r["held_on"] for r in agenda)

    # ── 부처 ──
    m_rows = []
    for e in data["ministries"]:
        mid = e["id"]
        tier = "core" if mid in core else ("adjacent" if mid in adjacent else "none")
        m_rows.append({"id": mid, "name": canonical_name(mid, latest),
                       "category": e.get("category"), "stc_tier": tier})
    dump_chunks("ministry", m_rows)

    # ── 회의 ──
    meetings: dict[str, dict] = {}
    for rec in manifest:
        e = meetings.setdefault(rec["meeting_key"], {"year": rec["year"], "session": rec["session"],
                                                     "date": rec["date"], "news_ids": {}})
        e["news_ids"][rec["doc_type"]] = rec["news_id"]
    mt_rows = []
    for k, e in sorted(meetings.items()):
        nid = e["news_ids"].get("브리핑") or next(iter(e["news_ids"].values()))
        mt_rows.append({"key": k, "year": e["year"], "session": e["session"],
                        "held_on": e["date"], "news_id": nid, "source_url": VIEW_URL + nid})
    dump_chunks("meeting", mt_rows)
    mkeys = set(meetings)

    # ── 안건 ──
    a_rows = []
    for r in agenda:
        if r["meeting_key"] not in mkeys:
            continue
        v = classify(r["title"], r.get("ministry_id"))
        a_rows.append({
            "meeting_key": r["meeting_key"], "bill_no": none_if_blank(r["bill_no"]),
            "category": r["category"], "title": r["title"],
            "ministry_id": r.get("ministry_id"), "submitter_raw": none_if_blank(r.get("submitter_raw")),
            "subject_org": none_if_blank(r.get("subject_org")), "held_on": r["held_on"],
            "role": role_of(r["category"], r["title"]), "is_stc": v.is_relevant,
            "stc_level": v.level if v.is_relevant else None, "tags": v.tags,
            "cabinet_result": none_if_blank(r.get("cabinet_result")),
        })
    n_a = dump_chunks("agenda_item", a_rows)

    # ── 발언 ──
    u_rows = []
    for r in utterances:
        if r["meeting_key"] not in mkeys:
            continue
        v = classify(r["text"], r.get("ministry_id"))
        u_rows.append({
            "meeting_key": r["meeting_key"], "ord": r.get("order"),
            "speaker_raw": r["speaker_raw"], "speaker_type": none_if_blank(r.get("speaker_type")),
            "ministry_id": r.get("ministry_id"), "held_on": r["held_on"],
            "attribution": r["attribution"], "is_stc": v.is_relevant,
            "tags": v.tags, "body": r["text"],
        })
    n_u = dump_chunks("utterance", u_rows)

    # ── 보고·토의 ──
    r_rows = []
    for r in reports:
        if r["meeting_key"] not in mkeys:
            continue
        v = classify(r["title"], r.get("ministry_id"))
        r_rows.append({
            "meeting_key": r["meeting_key"], "section": r["section"], "ord": r.get("order"),
            "title": r["title"], "ministry_id": r.get("ministry_id"),
            "ministry_raw": none_if_blank(r.get("ministry_raw")), "held_on": r["held_on"],
            "is_stc": v.is_relevant, "tags": v.tags,
        })
    dump_chunks("report_item", r_rows)

    print(f"REST JSON -> {OUT}")
    print(f"  ministry {len(m_rows)} · meeting {len(mt_rows)} · "
          f"agenda {len(a_rows):,}({n_a}p) · utterance {len(u_rows):,}({n_u}p) · report {len(r_rows)}")


if __name__ == "__main__":
    main()
