"""Phase 1 스텝 1: 브리핑 목록 수집."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.collect.briefing_list import collect, save
from src.collect.http import Fetcher
from src.normalize.meeting_key import parse_key, parse_doc_type

# 2018-09-04(제38회)부터 「의사일정」 첨부가 실린다 — 실측으로 확인한 경계.
# 그 전(2018-08 이전)은 「결과보도자료」만 있고 안건 전수 문서가 없어 같은
# 파이프라인으로 못 다룬다. "1998년부터"라는 이전 메모는 부정확했다: 목록
# 자체는 2004년부터고, 실제 안건 전수 추출이 가능한 구간은 2018-09부터다.
START, END = "2018-09-01", "2026-12-31"
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
