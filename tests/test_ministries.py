"""부처 정규화 회귀 방지.

여기 걸린 규칙이 무너지면 의제 점유 시계열이 조용히 틀어진다. 값이 이상해지는
게 아니라 **그럴듯하게 틀린 값**이 나오기 때문에 눈으로는 못 잡는다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.normalize.ministries import (  # noqa: E402
    canonical_name,
    comparability,
    resolve,
    science_tech_ids,
    validate_against_observed,
)


def test_개편_전후_이름이_같은_ID로_모인다():
    # 이게 깨지면 한 부처가 둘로 갈라져 각각 절반씩 세어진다.
    assert resolve("기획재정부") == resolve("기재부") == "moef"
    assert resolve("산업통상자원부") == resolve("산업통상부") == "motie"
    assert resolve("환경부") == resolve("기후에너지환경부") == "mcee"
    assert resolve("통계청") == resolve("국가데이터처") == "kdata"
    assert resolve("여성가족부") == resolve("성평등가족부") == "mogef"


def test_조판_공백이_섞여도_해석된다():
    # 의사일정 표는 셀 폭에 맞춰 기관명 중간에서 줄을 바꾼다.
    assert resolve("과학기술 정보통신부") == "msit"
    assert resolve("기후에너지\n환경부") == "mcee"
    assert resolve("문화체육 관광부") == "mcst"


def test_시점에_맞는_정식명칭을_돌려준다():
    assert canonical_name("motie", "2025-09-01") == "산업통상자원부"
    assert canonical_name("motie", "2025-10-01") == "산업통상부"
    assert canonical_name("mogef", "2026-01-01") == "성평등가족부"


def test_기재부_분리는_비교_불가로_경고된다():
    # 기획재정부 → 재정경제부 + 기획예산처. 2026-01-02를 걸치면 분모가 달라진다.
    result = comparability("moef", "2025-06-01", "2026-06-01")
    assert not result.comparable
    assert "split" in result.warning


def test_산업부_개명은_기능이관이므로_비교_불가다():
    # 겉보기엔 단순 개명이지만 에너지가 기후에너지환경부로 넘어갔다.
    # 이걸 놓치면 2025-10-01의 급락을 정책 변화로 오독한다.
    result = comparability("motie", "2025-06-01", "2026-06-01")
    assert not result.comparable
    assert "에너지" in result.warning


def test_단순_개명과_승격은_이어도_된다():
    assert comparability("mogef", "2025-06-01", "2026-06-01").comparable  # rename
    assert comparability("kdata", "2025-06-01", "2026-06-01").comparable  # elevated


def test_개편_구간_밖이면_비교_가능하다():
    assert comparability("motie", "2025-10-02", "2026-06-01").comparable
    assert comparability("msit", "2025-06-01", "2026-06-01").comparable


def test_미등록_기관은_조용히_넘어가지_않는다():
    problems = validate_against_observed([("있을리없는부", "2026-01-01")])
    assert len(problems) == 1
    assert problems[0]["issue"] == "미등록 기관"


def test_시점에_없던_이름은_불일치로_보고된다():
    # 재정경제부는 2026-01-02부터다. 2025년 문서에 나오면 표나 문서가 틀렸다.
    problems = validate_against_observed([("재정경제부", "2025-08-01")])
    assert len(problems) == 1
    problem = problems[0]
    assert problem["issue"] == "시점 불일치"
    assert problem["ministry_id"] == "moe_fin"
    # 그 이름이 유효한 구간을 그대로 보고한다. 2025-08은 그 밖이다.
    assert problem["valid_windows"] == ["2026-01-02~~"]


def test_정상_관측은_문제로_잡히지_않는다():
    assert validate_against_observed([("과학기술정보통신부", "2026-07-14")]) == []
    assert validate_against_observed([("산업통상자원부", "2025-08-01")]) == []


def test_대검찰청은_검찰청의_별칭이다():
    # 관행상 혼용되는 동일 기관. 공소청·중대범죄수사청 분리는 2026-09 예정이라
    # 그 전까지는 별도 lineage 이벤트 없이 하나로 취급한다.
    assert resolve("대검찰청") == resolve("검찰청") == "spo"


def test_국가인공지능전략위원회는_과기_핵심으로_분류된다():
    # AI기본법 제7조 근거 대통령 직속 기구 — 존재 목적이 AI 정책이므로
    # 부처보고·집중토의에 등판하면 제목 문구와 무관하게 핵심으로 잡혀야 한다.
    assert resolve("국가인공지능전략위원회") == "naisc"
    assert "naisc" in science_tech_ids(include_adjacent=False)


def test_식품의약품안전처_원문_오탈자가_흡수된다():
    # 2020-060 의사일정 원문 자체의 오탈자(처→저). 문서를 고치지 않고
    # 별칭으로만 흡수한다 — 조용히 다른 값으로 바꿔치기하지 않는다.
    assert resolve("식품의약품안전저") == resolve("식품의약품안전처") == "mfds"


def test_국가인권위원회가_등록되어_있다():
    assert resolve("국가인권위원회") == "nhrck"


def test_과기정책_범위에_예산과_규제가_포함된다():
    # R&D 예산은 기재부, 규제는 국무조정실 소관이다. 부처 화이트리스트만
    # 쓰면 과기정책의 급소를 놓친다.
    ids = science_tech_ids(include_adjacent=True)
    assert {"msit", "motie", "kdata"} <= ids
    assert {"moef", "opm"} <= ids
    core_only = science_tech_ids(include_adjacent=False)
    assert "moef" not in core_only
