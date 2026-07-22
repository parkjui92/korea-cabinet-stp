"""회의 식별키 파싱.

조인 키는 `(연도, 회차)`다. 회차는 해마다 1로 리셋되므로 연도 없는 회차는
키가 될 수 없다 — 2025년 제24회와 2026년 제24회가 모두 존재한다.

**회의 종류는 키가 아니다.** 실측 결과 정규 국무회의와 임시 국무회의는
회차 연번을 공유한다.

  2025년: 정규 ∪ 임시 = 제25~57회 (임시는 29·39회, 제35회만 결번)
  2026년: 정규 ∪ 임시 = 제1~32회  (임시는 8·12·15·32회, 결번 없음)

게다가 같은 회의의 문서끼리도 '임시' 표기가 흔들린다. 2026-04-11에는
`제15회 임시 국무회의 브리핑`과 `제15회 국무회의 결과 브리핑`이 나란히 올라와
있다. 종류를 키에 넣으면 이 한 회의가 둘로 갈라진다.

세 출처가 각기 다른 문자열로 같은 회의를 가리킨다.
  korea.kr : `제30회 국무회의 브리핑`            (+ 별도 필드로 날짜)
  행안부   : `2026년도 제23회 국무회의 회의록 (260526)`
  KTV      : `(26.7.14.) 이재명 대통령 제30회 국무회의`
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 회의 종류. '임시'는 별도 회차 계열을 쓰지 않고 같은 연번을 공유하지만,
# 성격이 다르므로 구분해 보관한다.
KIND_REGULAR = "국무회의"
KIND_EXTRAORDINARY = "임시국무회의"
KIND_VICE = "차관회의"

# 문서 유형 — 같은 회차에 '브리핑'과 '결과 브리핑'이 따로 올라온다.
DOC_BRIEFING = "브리핑"
DOC_RESULT_BRIEFING = "결과브리핑"
DOC_MINUTES = "회의록"

_SESSION_RE = re.compile(r"제\s*(\d+)\s*회")
_YEAR_RE = re.compile(r"(\d{4})\s*년")


@dataclass(frozen=True)
class MeetingKey:
    """회의 하나를 가리키는 키. 종류는 포함하지 않는다(모듈 docstring 참고)."""

    year: int
    session: int

    def __str__(self) -> str:
        return f"{self.year}-{self.session:03d}"


def parse_kind(title: str) -> str:
    """제목에서 회의 종류를 읽는다.

    '임시'는 `제32회 임시 국무회의` / `제32회 (임시)국무회의` 두 표기가 모두 쓰인다.
    """
    if "차관회의" in title:
        return KIND_VICE
    if "임시" in title:
        return KIND_EXTRAORDINARY
    return KIND_REGULAR


def parse_doc_type(title: str) -> str:
    if "회의록" in title:
        return DOC_MINUTES
    if "결과" in title:
        return DOC_RESULT_BRIEFING
    return DOC_BRIEFING


def parse_session(title: str) -> int | None:
    m = _SESSION_RE.search(title)
    return int(m.group(1)) if m else None


def parse_key(title: str, date_iso: str | None = None) -> MeetingKey | None:
    """제목(+날짜)에서 회의키를 만든다. 회차나 연도를 못 읽으면 None.

    연도는 제목에 `2026년도`가 있으면 그걸 쓰고, 없으면 날짜에서 가져온다.
    브리핑이 회의 다음 날 올라오는 경우가 있어 연말·연초에는 날짜 연도가
    회의 연도와 어긋날 수 있다 — 제목의 연도를 항상 우선한다.
    """
    session = parse_session(title)
    if session is None:
        return None

    year_match = _YEAR_RE.search(title)
    if year_match:
        year = int(year_match.group(1))
    elif date_iso:
        year = int(date_iso[:4])
    else:
        return None

    return MeetingKey(year=year, session=session)


def merge_kind(titles: list[str]) -> str:
    """한 회의에 딸린 문서 제목들에서 회의 종류를 판정한다.

    같은 회의라도 문서마다 '임시' 표기가 붙었다 빠졌다 한다(2026 제15회).
    하나라도 '임시'로 부르면 임시로 본다 — 정규 회의를 임시로 잘못 부르는
    일보다, 임시 회의에서 '임시'가 누락되는 일이 흔하다.
    """
    kinds = {parse_kind(t) for t in titles}
    if KIND_VICE in kinds:
        return KIND_VICE
    if KIND_EXTRAORDINARY in kinds:
        return KIND_EXTRAORDINARY
    return KIND_REGULAR
