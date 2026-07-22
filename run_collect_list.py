"""Phase 1 스텝 1: 브리핑 목록 수집."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.collect.briefing_list import collect, save
from src.collect.http import Fetcher
from src.normalize.meeting_key import parse_key, parse_doc_type

START, END = "2025-06-01", "2026-12-31"   # 현 정부 출범 이후
ROOT = Path(__file__).parent

fetcher = Fetcher(delay=1.5)
print(f"브리핑 목록 수집: {START} ~ {END}")
refs = collect(fetcher, START, END, snapshot_dir=ROOT / "data/raw/briefing_list")

out = ROOT / "data/export/briefing_index.jsonl"
save(refs, out)
print(f"\n총 {len(refs)}건 -> {out}")

# 회의키 파싱 성공률 즉시 점검
ok, fail = [], []
for r in refs:
    k = parse_key(r.title, r.date)
    (ok if k else fail).append(r)
print(f"회의키 파싱: 성공 {len(ok)} / 실패 {len(fail)}")
for r in fail[:10]:
    print(f"  [실패] {r.date} {r.title!r}")
