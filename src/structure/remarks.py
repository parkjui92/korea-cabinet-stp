"""「모두말씀」 문서에서 화자별 발언을 뽑는다.

KTV 자막은 `ko/asr(자동생성)`뿐이라 화자 분리가 없다. 3시간짜리 회의에서
누가 무슨 말을 했는지 추정하는 건 비싸고 틀리기 쉽다. 그런데 모두말씀 첨부는
화자를 명시한다.

    ▲ 이 대통령 : 그러니까 그런 한계가 있는 것 저도 알죠…
    - 윤호중 행안부 장관 : 대통령님, 지방정부는 자치권이 있어 가지고…

즉 모두발언 구간만큼은 **추정이 필요 없다.** 다만 문서 앞부분은 화자 표기 없이
문단만 이어지는데, 이건 문서 성격상(「모두말씀」) 대통령 발언이다. 추정이
아니라 문서 정의이므로 `document_default`로 구분해 기록한다.

발언마다 근거 등급을 남기는 이유: 나중에 이 데이터로 부처별 발언 점유를 재려면
"표기가 있어서 확실한 것"과 "문서 성격상 그럴 것"을 섞으면 안 된다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..normalize.ministries import resolve
from ..normalize.textnorm import collapse

# 화자 표기. `▲ 이 대통령 : `, `- 윤호중 행안부 장관 : `, `-이재명 대통령: `
_SPEAKER_RE = re.compile(
    r"^\s*[▲△▶●○■□◆◇\-•*]\s*([^:：]{2,30}?)\s*[:：]\s*(.*)$"
)

# 화자 문자열을 성명과 직위로 가른다. 성명이 `이`처럼 성만 나오기도 한다.
_NAME_ROLE_RE = re.compile(r"^([가-힣]{1,4})\s+(.*)$")

ATTR_EXPLICIT = "explicit"  # 문서에 화자가 적혀 있음
ATTR_DOCUMENT_DEFAULT = "document_default"  # 「모두말씀」이므로 대통령

# 화자 유형. 부처가 없는 화자를 '부처 미해결'로 잘못 세지 않기 위해 나눈다.
TYPE_PRESIDENT = "대통령"
TYPE_PM = "국무총리"
TYPE_MINISTER = "장관"
TYPE_MODERATOR = "진행"
TYPE_OTHER = "기타"

# 직위 문자열에 섞인 부처 약칭을 정식명으로 펴기 위한 최소 사전.
# ministries.yaml의 aliases로 대부분 풀리지만, 발언 표기에만 나오는 형태를 보탠다.
_ROLE_MINISTRY_HINTS = {
    "행안부": "행정안전부",
    "과기부": "과학기술정보통신부",
    "과기정통부": "과학기술정보통신부",
    "산업부": "산업통상부",
    "기재부": "기획재정부",
    "복지부": "보건복지부",
    "국토부": "국토교통부",
    "문체부": "문화체육관광부",
    "농식품부": "농림축산식품부",
    "해수부": "해양수산부",
    "여가부": "성평등가족부",
    "고용부": "고용노동부",
    "노동부": "고용노동부",
    "중기부": "중소벤처기업부",
    "기후부": "기후에너지환경부",
    "금융위": "금융위원회",
    "공정위": "공정거래위원회",
    "권익위": "국민권익위원회",
    "방통위": "방송미디어통신위원회",
    "식약처": "식품의약품안전처",
    "보훈부": "국가보훈부",
    "데이터처": "국가데이터처",
    "국조실": "국무조정실",
}


@dataclass
class Utterance:
    order: int
    speaker_raw: str
    speaker_name: str
    speaker_role: str
    ministry_id: str | None
    speaker_type: str
    text: str
    attribution: str

    @property
    def is_president(self) -> bool:
        return self.speaker_type == TYPE_PRESIDENT


def _split_name_role(speaker: str) -> tuple[str, str]:
    """`윤호중 행안부 장관` → (윤호중, 행안부 장관). `이 대통령` → (이, 대통령)."""
    text = collapse(speaker)
    m = _NAME_ROLE_RE.match(text)
    if not m:
        return "", text
    return m.group(1), m.group(2).strip()


def speaker_type(role: str) -> str:
    """화자 유형. 부처가 없는 화자를 '미해결'로 오분류하지 않기 위해 쓴다."""
    packed = re.sub(r"\s+", "", role or "")
    if "대통령" in packed and "부총리" not in packed:
        return TYPE_PRESIDENT
    if packed.startswith("국무총리") or packed == "국무총리":
        return TYPE_PM
    if packed.startswith("사회"):
        return TYPE_MODERATOR
    if any(packed.endswith(s) for s in ("장관", "위원장", "처장", "청장", "차관")):
        return TYPE_MINISTER
    return TYPE_OTHER


def _ministry_from_role(role: str, when: str | None = None) -> str | None:
    """직위 문자열에서 소속 부처를 읽는다.

    대통령·국무총리·진행자는 소관 부처가 없다 — None이 정상이며 결측이 아니다.
    겸직(`부총리 겸 기획재정부 장관`)은 뒤쪽 부처를 취한다.
    """
    kind = speaker_type(role)
    if kind in (TYPE_PRESIDENT, TYPE_PM, TYPE_MODERATOR):
        return None

    packed = re.sub(r"\s+", "", role or "")
    if not packed:
        return None

    # 겸직 표기는 `겸` 뒤가 실제 소관 부처다.
    if "겸" in packed:
        packed = packed.rsplit("겸", 1)[1]

    for short, full in _ROLE_MINISTRY_HINTS.items():
        if short in packed:
            return resolve(full, when)
    # `과학기술정보통신부 장관`처럼 정식명이 그대로 들어있는 경우.
    for suffix in ("장관", "위원장", "처장", "청장", "실장", "차관"):
        if packed.endswith(suffix):
            return resolve(packed[: -len(suffix)], when)
    return resolve(packed, when)


def parse_remarks(doc: dict, when: str | None = None) -> list[Utterance]:
    """모두말씀 문서를 발언 목록으로 바꾼다.

    표(제목 상자 등)는 건너뛰고 문단만 읽는다.
    """
    utterances: list[Utterance] = []
    # 첫 화자 표기가 나오기 전까지는 대통령 발언이다(문서 정의).
    current_speaker = "대통령"
    current_attr = ATTR_DOCUMENT_DEFAULT

    for block in doc.get("blocks", []):
        if block.get("type") == "table":
            continue
        for raw_line in (block.get("text") or "").split("\n"):
            line = collapse(raw_line)
            if not line or line in {"(끝)", "(끝)."}:
                continue

            m = _SPEAKER_RE.match(line)
            if m:
                current_speaker = collapse(m.group(1))
                current_attr = ATTR_EXPLICIT
                body = collapse(m.group(2))
                if not body:
                    continue
            else:
                body = line

            name, role = _split_name_role(current_speaker)
            utterances.append(
                Utterance(
                    order=len(utterances) + 1,
                    speaker_raw=current_speaker,
                    speaker_name=name,
                    speaker_role=role or current_speaker,
                    ministry_id=_ministry_from_role(role or current_speaker, when),
                    speaker_type=speaker_type(role or current_speaker),
                    text=body,
                    attribution=current_attr,
                )
            )

    return utterances
