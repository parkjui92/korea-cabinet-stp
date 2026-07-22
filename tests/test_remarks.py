"""모두말씀 화자 파싱 회귀 방지.

이 파서의 실패는 조용하다. 터지지 않고 **그럴듯하게 틀린 귀속**을 만든다.
실측(2023-049)에서 문서 머리의 일시·장소 줄이 화자로 잡혔고, 그 상태가
이어져 뒤 문단 40건이 통째로 가짜 화자에게 `explicit`으로 귀속됐다.
근거 등급이 `explicit`이면 "문서에 적혀 있으니 확실하다"는 뜻이라 더 위험하다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.structure.remarks import (  # noqa: E402
    ATTR_DOCUMENT_DEFAULT,
    ATTR_EXPLICIT,
    TYPE_MINISTER,
    TYPE_PRESIDENT,
    parse_remarks,
)


def _doc(lines: list[str]) -> dict:
    return {"blocks": [{"type": "paragraph", "text": "\n".join(lines)}]}


def test_일시_장소_줄을_화자로_잡지_않는다():
    # `- 2023. 11. 22(수) 08:00, 정부서울청사 -`
    # 기호 `-`로 시작하고 시각의 `:`가 있어 화자 표기와 모양이 같다.
    doc = _doc(
        [
            "제49회 임시국무회의",
            "- 2023. 11. 22(수) 08:00, 정부서울청사 -",
            "지금부터 제49회 국무회의를 시작하겠습니다.",
        ]
    )
    utterances = parse_remarks(doc, when="2023-11-22")
    assert all(u.speaker_type == TYPE_PRESIDENT for u in utterances)
    # 가짜 화자가 상태를 오염시키지 않았는지 — 전부 문서기본이어야 한다.
    assert all(u.attribution == ATTR_DOCUMENT_DEFAULT for u in utterances)
    assert not any("2023" in u.speaker_raw for u in utterances)


def test_진짜_화자_표기는_여전히_잡힌다():
    doc = _doc(
        [
            "올 상반기 수출이 늘었습니다.",
            "- 윤호중 행안부 장관 : 대통령님, 지방정부는 자치권이 있어서",
            "▲ 이 대통령 : 그 한계는 저도 압니다.",
        ]
    )
    utterances = parse_remarks(doc, when="2026-07-14")
    assert utterances[0].attribution == ATTR_DOCUMENT_DEFAULT
    assert utterances[0].speaker_type == TYPE_PRESIDENT

    minister = utterances[1]
    assert minister.attribution == ATTR_EXPLICIT
    assert minister.speaker_name == "윤호중"
    assert minister.speaker_type == TYPE_MINISTER
    assert minister.ministry_id == "mois"

    president = utterances[2]
    assert president.attribution == ATTR_EXPLICIT
    assert president.speaker_type == TYPE_PRESIDENT
    assert president.ministry_id is None


def test_공백없는_표기도_잡힌다():
    doc = _doc(["-이재명 대통령: 벌써 1년이 됐습니다."])
    utterances = parse_remarks(doc, when="2025-12-02")
    assert utterances[0].attribution == ATTR_EXPLICIT
    assert utterances[0].speaker_type == TYPE_PRESIDENT


def test_화자_표기_전까지는_대통령_발언이다():
    # 「모두말씀」은 문서 성격상 대통령 발언이다. 추정이 아니라 문서 정의라
    # `document_default`로 표시하되 화자는 대통령으로 둔다.
    doc = _doc(["첫 문단입니다.", "둘째 문단입니다.", "▲ 이 대통령 : 셋째입니다."])
    utterances = parse_remarks(doc, when="2026-01-01")
    assert [u.attribution for u in utterances] == [
        ATTR_DOCUMENT_DEFAULT,
        ATTR_DOCUMENT_DEFAULT,
        ATTR_EXPLICIT,
    ]
    assert all(u.speaker_type == TYPE_PRESIDENT for u in utterances)
