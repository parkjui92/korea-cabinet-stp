"""안건의 역할 구분 — 의제 점유를 정직하게 재기 위한 전처리.

제출기관을 그대로 세면 부처 간 의제 점유가 크게 왜곡된다. 실측(2,190건):

    법제처   886건(40.5%)  ← 그중 870건이 법률공포안
    행정안전부 325건(14.8%) ← 그중 146건이 타 부처 직제 개정령

둘 다 **형식적 통로**다. 법률공포안은 국회를 통과한 법률을 공포하는 절차이지
법제처의 정책 발의가 아니고, 직제령은 행안부가 정부조직 관리자로서 타 부처
조직 변경을 대신 올리는 것이다.

이걸 걸러내면 그림이 완전히 달라진다. 과기정통부 34건·산업통상부 43건·
기후에너지환경부 59건은 전부 실질 정책 안건이라 상대적 비중이 크게 오른다.

어느 쪽을 분모로 쓸지는 연구 질문에 달렸으므로, 여기서는 **역할을 라벨링만**
하고 집계에서 고르게 한다.
"""

from __future__ import annotations

import re

ROLE_POLICY = "정책안건"  # 부처가 실질적으로 발의한 정책
ROLE_PROMULGATION = "법률공포"  # 국회 통과 법률의 공포 절차 (법제처 일괄)
ROLE_ORGANIZATION = "조직직제"  # 타 부처 직제 개정 (행안부 일괄)
ROLE_PERSONNEL = "인사"  # 정부인사발령·영예수여 등

_ORG_RE = re.compile(r"직제\s*(일부)?개정령안|직제령")
_PERSONNEL_RE = re.compile(r"정부인사발령|영예수여|서훈|포상")


def role_of(category: str, title: str) -> str:
    """안건 하나의 역할을 판정한다."""
    if category == "법률공포안":
        return ROLE_PROMULGATION
    if _ORG_RE.search(title or ""):
        return ROLE_ORGANIZATION
    if _PERSONNEL_RE.search(title or ""):
        return ROLE_PERSONNEL
    return ROLE_POLICY
