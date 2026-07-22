"""의사일정 파서 회귀 방지.

기준값은 제30회 국무회의(2026-07-14) 결과 보도자료의 공식 문장에서 왔다.

    △법률안 3건, △대통령령안 18건, △일반안건 6건을 심의․의결하였습니다

이 27건이 안건 점유 분석의 분모다. 파서가 한 건이라도 흘리면 모든 비율이
틀어지므로 실제 문서로 고정해 둔다.
"""

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collect.agenda_doc import parse_bill_table  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "agenda_2026_030.json"


def _items():
    blocks = json.loads(FIXTURE.read_text(encoding="utf-8"))["blocks"]
    bill_table = max(
        (b for b in blocks if b["type"] == "table"), key=lambda b: b["table"]["rows"]
    )
    return parse_bill_table(bill_table)


def test_안건_전수와_유형별_건수가_공식_발표와_일치한다():
    items = _items()
    counts = collections.Counter(i.category for i in items)
    assert len(items) == 27
    assert counts["법률안"] == 3
    assert counts["대통령령안"] == 18
    assert counts["일반안건"] == 6


def test_반복기호로_생략된_제출일과_제출기관이_채워진다():
    # 1187·1188은 제출월일·제출기관이 모두 〃로 생략돼 1186을 승계한다.
    items = {i.bill_no: i for i in _items()}
    for bill_no in ("1186", "1187", "1188"):
        assert items[bill_no].submitted_on == "2026-07-07"
        assert items[bill_no].submitter == "문화체육관광부"


def test_기관명_중간의_줄바꿈이_제거된다():
    # 셀 폭 때문에 `과학기술\n정보통신부`로 조판된다.
    items = {i.bill_no: i for i in _items()}
    assert items["1189"].submitter == "과학기술정보통신부"
    assert items["1201"].submitter == "기후에너지환경부"
    assert all(" " not in i.submitter for i in _items())


def test_국무총리_대리제출은_괄호_안_실소관으로_귀속된다():
    # 원문 `국무총리(국가데이터처)` — 통계로 집계할 땐 국가데이터처가 맞다.
    items = {i.bill_no: i for i in _items()}
    assert items["1206"].submitter == "국가데이터처"
    assert "국무총리" in items["1206"].submitter_raw
    assert items["1205"].submitter == "공정거래위원회"


def test_즉석안건은_차관회의_결과를_지어내지_않는다():
    # 1211·1212는 차관회의를 거치지 않아 칸이 실제로 비어 있다.
    # 〃 승계 로직이 위 값을 흘려 넣으면 없는 의결이 생긴다.
    items = {i.bill_no: i for i in _items()}
    assert items["1210"].vice_result == "원안의결"
    assert items["1211"].vice_result == ""
    assert items["1212"].vice_result == ""


def test_의결결과의_반복기호는_해소된다():
    assert all("〃" not in i.vice_result for i in _items())


def test_과기정통부_안건이_정확히_식별된다():
    items = [i for i in _items() if i.submitter == "과학기술정보통신부"]
    assert len(items) == 1
    assert items[0].bill_no == "1189"
    assert items[0].category == "대통령령안"
    assert "인공지능" in items[0].title
