"""korea.kr 국무회의 브리핑 목록 수집.

주의할 점 두 가지가 실측으로 확인됐다.

1. 목록은 `startDate`/`endDate`가 없으면 **최근 1년만** 보여준다. 기본값으로
   호출하면 69건이 나오지만 실제 아카이브는 1998년까지 1,498건이다.
2. 한 페이지(32건)에 컨테이너가 두 개다. 상단 강조 영역
   `div.article_head ul.lst_col2 > li`(2건)와 본 목록
   `table.table_list td.subject`(30건). 둘은 겹칠 수 있으므로 newsId로 중복을 지운다.

목록 항목은 브리핑 본문 앞부분을 `span.lead`에 담고 있어 상세 페이지 없이도
어느 정도 읽히지만, 전체 안건은 담기지 않는다(제30회는 27건 의결 중 소관
태그 6개뿐). 안건 전수는 첨부 문서에서 얻는다.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from .http import Fetcher

LIST_URL = "https://www.korea.kr/briefing/stateCouncilList.do"
VIEW_URL = "https://www.korea.kr/briefing/stateCouncilView.do"

_NEWS_ID_RE = re.compile(r"newsId=(\d+)")
_TOTAL_RE = re.compile(r"총\s*<strong>(\d+)</strong>\s*건")
_DATE_RE = re.compile(r"(\d{4})[.\-](\d{2})[.\-](\d{2})")


@dataclass
class BriefingRef:
    """목록 한 줄. 상세를 아직 안 읽은 상태의 참조."""

    news_id: str
    title: str
    date: str | None  # ISO yyyy-mm-dd
    lead: str  # 본문 앞부분(잘려 있을 수 있음)

    @property
    def url(self) -> str:
        return f"{VIEW_URL}?newsId={self.news_id}"


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def _to_iso(raw: str) -> str | None:
    m = _DATE_RE.search(raw)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def parse_list_page(html: str) -> list[BriefingRef]:
    """한 페이지에서 브리핑 참조를 뽑는다. 두 컨테이너를 모두 훑는다."""
    soup = BeautifulSoup(html, "lxml")
    refs: dict[str, BriefingRef] = {}

    for anchor in soup.find_all("a"):
        onclick = anchor.get("onclick") or ""
        if "goView" not in onclick:
            continue
        m = _NEWS_ID_RE.search(onclick)
        if not m:
            continue
        news_id = m.group(1)
        if news_id in refs:
            continue

        title = _text(anchor.find("strong"))
        if not title:
            # 본 목록(table)은 strong 없이 제목을 직접 담는 경우가 있다.
            title = _text(anchor)
        lead = _text(anchor.find("span", class_="lead"))
        source = _text(anchor.find("span", class_="source"))

        date = _to_iso(source)
        if date is None:
            # table 레이아웃은 날짜가 형제 <td>에 있다.
            row = anchor.find_parent("tr")
            if row:
                date = _to_iso(_text(row))

        refs[news_id] = BriefingRef(news_id=news_id, title=title, date=date, lead=lead)

    return list(refs.values())


def total_count(html: str) -> int | None:
    m = _TOTAL_RE.search(html)
    return int(m.group(1)) if m else None


def collect(
    fetcher: Fetcher,
    start: str,
    end: str,
    snapshot_dir: Path | None = None,
    max_pages: int = 200,
) -> list[BriefingRef]:
    """기간 내 브리핑 목록을 전부 모은다.

    `총 N건`을 먼저 읽어 기대 페이지 수를 정하고, 새 항목이 안 나오면 멈춘다.
    페이지 범위를 넘겨도 서버가 조용히 뭔가를 돌려주는 경우가 있어
    건수만 믿지 않고 '새 항목 없음'을 종료 조건으로 함께 쓴다.
    """
    collected: dict[str, BriefingRef] = {}
    expected: int | None = None

    for page in range(1, max_pages + 1):
        html = fetcher.get(
            LIST_URL,
            params={"startDate": start, "endDate": end, "pageIndex": page},
        )
        if snapshot_dir:
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            (snapshot_dir / f"list_{start}_{end}_p{page:03d}.html").write_text(
                html, encoding="utf-8"
            )

        if expected is None:
            expected = total_count(html)

        page_refs = parse_list_page(html)
        fresh = [r for r in page_refs if r.news_id not in collected]
        for ref in fresh:
            collected[ref.news_id] = ref

        print(
            f"  page {page:>3}: {len(page_refs):>2}건 파싱, 신규 {len(fresh):>2}건 "
            f"(누적 {len(collected)}{'/' + str(expected) if expected else ''})"
        )

        if not fresh:
            break
        if expected is not None and len(collected) >= expected:
            break

    return list(collected.values())


def save(refs: list[BriefingRef], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for ref in sorted(refs, key=lambda r: (r.date or "", r.news_id)):
            f.write(json.dumps(asdict(ref), ensure_ascii=False) + "\n")
