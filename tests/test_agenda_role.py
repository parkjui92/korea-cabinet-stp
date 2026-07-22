"""안건 역할 구분 회귀 방지.

이 구분이 무너지면 부처 간 의제 점유가 형식적 통로에 잠식된다. 실측에서
법제처가 40.5%로 1위였는데 그중 870/886이 법률공포안이었다 — 법제처의 정책
발의가 아니라 국회 통과 법률의 공포 절차다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.classify.agenda_role import (  # noqa: E402
    ROLE_ORGANIZATION,
    ROLE_PERSONNEL,
    ROLE_POLICY,
    ROLE_PROMULGATION,
    role_of,
)


def test_법률공포안은_정책안건이_아니다():
    # 국회를 통과한 법률의 공포 절차. 법제처가 일괄 제출한다.
    assert role_of("법률공포안", "상법 일부개정법률 공포안") == ROLE_PROMULGATION


def test_타부처_직제령은_조직직제로_분리된다():
    # 행안부가 정부조직 관리자로서 대신 올린다. 행안부의 정책 의제가 아니다.
    assert role_of("대통령령안", "교육부와 그 소속기관 직제 일부개정령안") == ROLE_ORGANIZATION
    assert role_of("대통령령안", "보건복지부와 그 소속기관 직제 일부개정령안") == ROLE_ORGANIZATION


def test_인사_안건은_따로_센다():
    assert role_of("일반안건", "영예수여안") == ROLE_PERSONNEL
    assert role_of("일반안건", "정부인사발령(안)") == ROLE_PERSONNEL


def test_실질_정책_안건은_정책안건이다():
    assert (
        role_of("대통령령안", "인공지능 발전과 신뢰 기반 조성 등에 관한 기본법 시행령 일부개정령안")
        == ROLE_POLICY
    )
    assert role_of("법률안", "국가유산수리 등에 관한 법률 일부개정법률안") == ROLE_POLICY
    assert role_of("일반안건", "2026년도 예산배정계획(안)") == ROLE_POLICY


def test_제목에_직제가_있어도_직제령이_아니면_정책안건이다():
    # `직제`라는 낱말만으로 잘라내면 안 된다.
    assert role_of("일반안건", "공공기관 직제 개선 연구용역 결과보고") == ROLE_POLICY
