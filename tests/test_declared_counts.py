"""선언 건수 집계 회귀 방지.

이 로직은 두 번 깨졌다. 둘 다 "그럴듯하게 틀린" 종류라 눈으로는 못 잡았다.

  1. `setdefault`로 첫 선언만 잡아, 같은 유형이 두 표에 쪼개져 나오면
     뒤 표를 놓쳤다(2024-042: 일반안건 3건+10건 → 3건만 셈).
  2. 그걸 합산으로 고쳤더니, 이번엔 표 앞 문단 라벨과 표 안 구분행이
     **같은 선언을 두 번** 말하는 걸 둘 다 더해 정확히 2배가 됐다
     (2024-042: 법률공포안 3건 → 6건). 444개 회의 전부가 불일치로 뒤집혔다.

핵심 규칙: `parse_agenda_items`가 category를 정하는 우선순위와 **똑같이** 센다.
표 안 구분행이 있으면 그것만, 없을 때만 앞 문단 라벨.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collect.agenda_doc import declared_counts  # noqa: E402


def _para(text: str) -> dict:
    return {"type": "paragraph", "text": text}


def _bill_table(rows: list[list[str]], cols: int = 6) -> dict:
    """머리행에 `의안번호`가 있어야 의안 표로 인식된다."""
    head = ["의안번호", "제출월일", "제출기관", "의안명", "차관회의", "국무회의"]
    cells = [[{"text": h, "colSpan": 1} for h in head]]
    for row in rows:
        if len(row) == 1:
            cells.append([{"text": row[0], "colSpan": cols}])
        else:
            cells.append([{"text": c, "colSpan": 1} for c in row])
    return {"type": "table", "table": {"rows": len(cells), "cols": cols, "cells": cells}}


def test_구분행이_있으면_앞_문단_라벨은_세지_않는다():
    # 실측 2024-042: 문단 `○ 법 률 공 포 안 : 3건`과 구분행 `법률공포안 (3건)`이
    # 같은 3건을 가리킨다. 둘 다 더하면 6건이 되어 전 회의가 불일치로 뒤집힌다.
    doc = {
        "blocks": [
            _para("○ 법 률 공 포 안 : 3건"),
            _bill_table([["법  률  공  포  안 (3건 )"], ["1", "", "", "가", "", ""]]),
        ]
    }
    assert declared_counts(doc) == {"법률공포안": 3}


def test_구분행이_없으면_앞_문단_라벨을_쓴다():
    # hwp본의 흔한 형태 — 표 전체가 한 유형이라 구분행을 생략한다(2025-031).
    doc = {
        "blocks": [
            _para("○ 법 률 공 포 안 : 16건"),
            _bill_table([["990", "", "", "상법 공포안", "", ""]]),
        ]
    }
    assert declared_counts(doc) == {"법률공포안": 16}


def test_같은_유형이_다른_표에_나뉘면_합산한다():
    # 실측 2024-042: 일반안건이 두 의안 표에 3건 + 10건으로 쪼개져 있다.
    doc = {
        "blocks": [
            _bill_table([["일   반   안   건 (3건 )"], ["1", "", "", "가", "", ""]]),
            _para("○ 차관회의 심의안건 : 26건"),
            _bill_table([["일   반   안   건 ( 10건 )"], ["2", "", "", "나", "", ""]]),
        ]
    }
    assert declared_counts(doc) == {"일반안건": 13}


def test_표지_요약표는_세지_않는다():
    # 표지(일시·장소와 함께 건수를 다시 적는 표)는 본문과 같은 숫자를
    # 중복 선언한다(2018-054: 법률공포안 103건이 표지·본문에 각각).
    cover = {
        "type": "table",
        "table": {
            "rows": 2,
            "cols": 4,
            "cells": [
                [{"text": "제54회 국무회의 의사일정", "colSpan": 4}],
                [{"text": "○ 의안", "colSpan": 1}, {"text": "-", "colSpan": 1},
                 {"text": "법  률  공  포 안 : 103건", "colSpan": 1}, {"text": "", "colSpan": 1}],
            ],
        },
    }
    doc = {
        "blocks": [
            cover,
            _bill_table([["법  률  공  포  안 (103건 )"], ["1", "", "", "가", "", ""]]),
        ]
    }
    assert declared_counts(doc) == {"법률공포안": 103}


def test_절차_구분_문단은_유형_선언이_아니다():
    # `차관회의 심의안건`은 절차이지 의안 유형이 아니다. 유형은 표 안에서 정해진다.
    doc = {
        "blocks": [
            _para("○ 차관회의 심의안건 : 25건 / 국무회의 즉석안건 : 2건"),
            _bill_table([["대  통  령  령 안 (18건 )"], ["1", "", "", "가", "", ""]]),
        ]
    }
    assert declared_counts(doc) == {"대통령령안": 18}


def test_건수_없는_라벨은_선언으로_치지_않는다():
    # hwpx본은 `○ 법 률 공 포 안`처럼 건수를 안 붙인다(2026-024).
    # '주장 없음'이지 '0건 주장'이 아니므로 집계에 넣지 않는다.
    doc = {
        "blocks": [
            _para("○ 법 률 공 포 안"),
            _bill_table([["1", "", "", "가", "", ""]]),
        ]
    }
    assert declared_counts(doc) == {}


def test_일반안_표기는_일반안건으로_정규화된다():
    doc = {"blocks": [_para("○ 일 반 안 : 6건"), _bill_table([["1", "", "", "가", "", ""]])]}
    assert declared_counts(doc) == {"일반안건": 6}
