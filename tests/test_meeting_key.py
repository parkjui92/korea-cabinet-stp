"""회의키 규칙 고정.

여기서 검증하는 규칙은 실측에서 나왔고, 틀리면 서로 다른 회의가 하나로
합쳐지거나 한 회의가 둘로 갈라진다. 조인의 토대라 회귀를 막아둔다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.normalize.meeting_key import (  # noqa: E402
    DOC_BRIEFING,
    DOC_MINUTES,
    DOC_RESULT_BRIEFING,
    KIND_EXTRAORDINARY,
    KIND_REGULAR,
    MeetingKey,
    merge_kind,
    parse_doc_type,
    parse_key,
    parse_kind,
)


def test_회차는_연도별로_리셋되므로_연도가_키에_포함된다():
    # 2025-12-31 제57회 다음이 2026-01-13 제1회다. 연도 없이는 구분 불가.
    assert parse_key("제57회 국무회의 브리핑", "2025-12-31") == MeetingKey(2025, 57)
    assert parse_key("제1회 국무회의 브리핑", "2026-01-13") == MeetingKey(2026, 1)


def test_정규와_임시는_회차_연번을_공유하므로_같은_키가_된다():
    # 2026-04-11에 두 문서가 같은 회의를 가리킨다. 종류가 키에 끼면 갈라진다.
    a = parse_key("제15회 임시 국무회의 브리핑", "2026-04-11")
    b = parse_key("제15회 국무회의 결과 브리핑", "2026-04-11")
    assert a == b == MeetingKey(2026, 15)


def test_제목의_연도가_날짜보다_우선한다():
    # 행안부 회의록은 게시일이 회의보다 한참 뒤라 날짜 연도를 믿을 수 없다.
    key = parse_key("2025년도 제57회 국무회의 회의록 (251231)", "2026-01-20")
    assert key == MeetingKey(2025, 57)


def test_회차를_못_읽으면_None():
    assert parse_key("국무회의 브리핑", "2026-07-14") is None


def test_연도도_날짜도_없으면_None():
    assert parse_key("제30회 국무회의 브리핑", None) is None


def test_회의_종류_판정():
    assert parse_kind("제32회 임시 국무회의 브리핑") == KIND_EXTRAORDINARY
    assert parse_kind("제32회 (임시)국무회의 브리핑") == KIND_EXTRAORDINARY
    assert parse_kind("제31회 국무회의 브리핑") == KIND_REGULAR


def test_문서_유형_판정():
    assert parse_doc_type("제29회 국무회의 브리핑") == DOC_BRIEFING
    assert parse_doc_type("제29회 국무회의 결과 브리핑") == DOC_RESULT_BRIEFING
    assert parse_doc_type("2026년도 제23회 국무회의 회의록 (260526)") == DOC_MINUTES


def test_문서마다_임시_표기가_흔들려도_회의는_임시로_판정된다():
    titles = ["제15회 임시 국무회의 브리핑", "제15회 국무회의 결과 브리핑"]
    assert merge_kind(titles) == KIND_EXTRAORDINARY


def test_모두_정규면_정규():
    assert merge_kind(["제31회 국무회의 브리핑", "제31회 국무회의 결과 브리핑"]) == KIND_REGULAR
