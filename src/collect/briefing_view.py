"""브리핑 상세 페이지에서 본문과 첨부 목록을 뽑는다.

첨부는 회차마다 이름이 조금씩 다르다(`제30회 국무회의 의사일정-배포용.hwp`,
`의사일정(제30회).hwp`, …). 파일명 전체를 믿지 말고 핵심어로 종류를 가른다.

같은 문서가 `.hwp`와 `.hwpx`로 함께 올라오기도 한다. hwpx가 있으면 그쪽을
쓴다 — ZIP+XML이라 구조가 안정적이고 파싱이 덜 깨진다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from ..normalize.textnorm import collapse

DOWNLOAD_URL = "https://www.korea.kr/common/download.do"

_FILE_ID_RE = re.compile(r"fileId=(\d+)")

# 첨부 종류. 값이 클수록 우선 수집.
KIND_AGENDA = "의사일정"  # 안건 전수 — 유일 출처
KIND_REMARKS = "모두말씀"  # 발언 공식 원문(화자 구분)
KIND_PRESS = "결과보도자료"  # 주요 안건 상세 설명
KIND_OTHER = "기타"

_KIND_PATTERNS = [
    (KIND_AGENDA, re.compile(r"의사\s*일정")),
    (KIND_REMARKS, re.compile(r"모두\s*(말씀|발언)")),
    (KIND_PRESS, re.compile(r"(결과|보도)\s*(참고)?\s*자료|보도참고")),
]

WANTED_KINDS = (KIND_AGENDA, KIND_REMARKS, KIND_PRESS)


@dataclass
class Attachment:
    file_id: str
    filename: str
    kind: str

    @property
    def ext(self) -> str:
        return self.filename.rsplit(".", 1)[-1].lower() if "." in self.filename else ""

    @property
    def url(self) -> str:
        return f"{DOWNLOAD_URL}?fileId={self.file_id}"


def classify(filename: str) -> str:
    name = collapse(filename)
    for kind, pattern in _KIND_PATTERNS:
        if pattern.search(name):
            return kind
    return KIND_OTHER


def parse_attachments(html: str) -> list[Attachment]:
    """상세 페이지에서 첨부를 뽑는다. `내려받기` 같은 빈 라벨은 버린다."""
    soup = BeautifulSoup(html, "lxml")
    found: dict[str, Attachment] = {}

    for anchor in soup.find_all("a"):
        href = anchor.get("href") or ""
        if "download.do" not in href:
            continue
        m = _FILE_ID_RE.search(href)
        if not m:
            continue
        label = collapse(anchor.get_text())
        # 같은 fileId가 파일명 링크와 `내려받기` 버튼 두 번 나온다.
        # 확장자가 있는 쪽이 진짜 파일명이다.
        if m.group(1) in found and "." not in label:
            continue
        if "." not in label:
            continue
        found[m.group(1)] = Attachment(
            file_id=m.group(1), filename=label, kind=classify(label)
        )

    return list(found.values())


def pick_wanted(attachments: list[Attachment]) -> list[Attachment]:
    """종류별로 한 개씩 고른다. 같은 종류면 hwpx > hwp > 그 외."""
    priority = {"hwpx": 0, "hwp": 1}
    chosen: dict[str, Attachment] = {}

    for att in attachments:
        if att.kind not in WANTED_KINDS:
            continue
        current = chosen.get(att.kind)
        if current is None or priority.get(att.ext, 9) < priority.get(current.ext, 9):
            chosen[att.kind] = att

    return [chosen[k] for k in WANTED_KINDS if k in chosen]


def extract_body(html: str) -> str:
    """브리핑 본문 텍스트. 과(課) 단위 소관 태그가 여기 있다."""
    soup = BeautifulSoup(html, "lxml")
    for selector in ("div.article_body", "div.view_cont", "#article_body"):
        node = soup.select_one(selector)
        if node:
            return collapse(node.get_text(" "))
    return collapse(soup.get_text(" "))
