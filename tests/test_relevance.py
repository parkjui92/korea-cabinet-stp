"""과기정책 관련성 분류 회귀 방지.

이 분류기가 존재하는 이유는 소관부처만 보면 놓치기 때문이다. 실측에서
opencabinet 지시-이행 트래커의 과기정통부는 3건, 산업부는 17건이었다 —
과기 신호가 부처 필터 밖에 있었다는 뜻이다.

그래서 여기 테스트의 절반은 '다른 부처 소관인데 과기정책인 건'을 다룬다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.classify.relevance import ADJACENT, CORE, UNRELATED, classify, match_tags  # noqa: E402


def test_과기_핵심부처_소관이면_주제어_없이도_핵심이다():
    v = classify("국가통계위원회 규정 일부개정령안", ministry_id="kdata")
    assert v.level == CORE
    assert any("소관부처(핵심)" in r for r in v.reasons)


def test_강한_주제어는_소관부처와_무관하게_핵심이다():
    v = classify(
        "인공지능 발전과 신뢰 기반 조성 등에 관한 기본법 시행령 일부개정령안",
        ministry_id="msit",
    )
    assert v.level == CORE
    assert "AI" in v.tags


def test_기재부_소관_RnD예산이_연관으로_잡힌다():
    # 부처 화이트리스트만 쓰면 놓치는 대표 사례.
    v = classify("2026년도 국가연구개발사업 예산 배분·조정안", ministry_id="moef")
    assert v.level in (CORE, ADJACENT)
    assert "R&D예산" in v.tags


def test_국무조정실_소관_규제혁신이_연관으로_잡힌다():
    v = classify("규제샌드박스 운영 개선방안", ministry_id="opm")
    assert v.level in (CORE, ADJACENT)
    assert "규제혁신" in v.tags


def test_국토부_소관_도심항공교통이_잡힌다():
    # 실제 제30회 안건. 소관은 국토교통부지만 과기정책 의제다.
    v = classify(
        "도심항공교통 활용 촉진 및 지원에 관한 법률 시행령 일부개정령안",
        ministry_id="molit",
    )
    assert v.level in (CORE, ADJACENT)
    assert "우주항공" in v.tags


def test_무관한_안건은_무관으로_남는다():
    assert classify("영예수여안", ministry_id="mois").level == UNRELATED
    assert classify("국세물납증권 매각(안)", ministry_id="moe_fin").level == UNRELATED


def test_짧은_라틴약어는_단어경계를_지킨다():
    # 'AI'가 'CHAIN'·'TRAINING' 같은 데 걸리면 오탐이 쏟아진다.
    tags, _, _ = match_tags("SUPPLY CHAIN TRAINING PLAN")
    assert "AI" not in tags
    tags, _, _ = match_tags("AI 기반 행정 혁신")
    assert "AI" in tags


def test_한글_붙여쓰기_변형을_흡수한다():
    for text in ("데이터센터 집적단지", "데이터 센터 집적단지"):
        tags, _, _ = match_tags(text)
        assert "데이터" in tags


def test_판정에는_반드시_근거가_붙는다():
    # 근거 없는 라벨은 검증이 불가능해 연구에 못 쓴다.
    v = classify("인공지능 기본법 시행령", ministry_id="msit")
    assert v.reasons
    assert classify("영예수여안", ministry_id="mois").reasons == []


def test_소관미상이어도_강태그면_핵심이다():
    v = classify("반도체 특별법 시행령 일부개정령안", ministry_id=None)
    assert v.level == CORE
    assert "반도체" in v.tags


def test_소관이_넓은_부처는_태그없이_핵심으로_잡히지_않는다():
    # motie·mcee·mss는 소관이 넓어 과기정책이 일부일 뿐이다. 예산소진성
    # 실측에서 이 셋을 science_tech_core에 뒀더니 태그 없이 core로 잡힌
    # 안건이 각각 74%·80%·97%였고, 내용은 무역·환경규제·소상공인지원이라
    # 과기정책이 아니었다. 반드시 주제 태그가 있어야 잡혀야 한다.
    assert classify("자유무역지역의 지정 및 운영에 관한 법률 시행령 일부개정령안", ministry_id="motie").level == UNRELATED
    assert classify("대기환경보전법 시행령 일부개정령안", ministry_id="mcee").level == UNRELATED
    assert classify("소상공인시장진흥기금운용계획 변경(안)", ministry_id="mss").level == UNRELATED


def test_소관이_넓은_부처도_주제어가_있으면_잡힌다():
    # 태그가 있으면 여전히 잡혀야 한다 — adjacent 강등이 신호 자체를 죽이면 안 된다.
    v1 = classify("희토류 공급망 안정화 대책", ministry_id="motie")
    assert v1.is_relevant and "반도체" in v1.tags  # 핵심광물은 반도체·배터리 공급망 원료
    v2 = classify("국민주권정부 에너지 대전환 추진계획", ministry_id="mcee")
    assert v2.is_relevant and "에너지" in v2.tags
    v3 = classify("중소기업 기술탈취 근절 그간성과 및 보완과제", ministry_id="mss")
    assert v3.is_relevant and "지식재산" in v3.tags  # 산업기술보호는 지식재산 보호의 일종


def test_전력_동음이의어를_에너지로_오탐하지_않는다():
    # 全力(전력투구·전력해 주시기)과 電力은 표기가 같다. 실측에서 대통령
    # 발언 11회 중 5회가 全力이었다. 단독 `전력`을 키워드로 쓰면 안 된다.
    for text in ("내각 전 부처가 전력투구해 주시기 바랍니다", "조속한 정상화에 전력해 주십시오"):
        tags, _, _ = match_tags(text)
        assert "에너지" not in tags, text
    # 電力 의미가 확정되는 복합어는 잡혀야 한다.
    assert "에너지" in match_tags("전력수급 기본계획 수립")[0]
    assert "에너지" in match_tags("전력망 확충 특별법")[0]
