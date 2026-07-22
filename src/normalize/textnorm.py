"""한글 공문서 표에서 나오는 텍스트 정규화.

정부 문서의 표는 조판을 위해 글자 사이에 공백을 넣고(`의 안 번 호`), 셀 폭에
맞춰 줄을 바꾸며(`과학기술\n정보통신부`), 같은 값이 이어지면 반복 기호(`〃`)로
줄인다. 셀 문자열을 그대로 키로 쓰면 전부 다른 값이 된다.
"""

from __future__ import annotations

import re

# 같음 표시. 한글 문서마다 다른 글자를 쓰므로 코드포인트로 못박는다.
#   U+3003 〃 · U+2033 ″ · U+201D ” · U+201C “ · U+3006 〆
DITTO_MARKS = {
    "〃",
    "″",
    "”",
    "“",
    '"',
    "^",
}

_WS_RE = re.compile(r"\s+")
_BR_RE = re.compile(r"<br\s*/?>", re.I)


def collapse(text: str | None) -> str:
    """줄바꿈·연속 공백을 공백 하나로 접고 앞뒤를 자른다."""
    if not text:
        return ""
    return _WS_RE.sub(" ", _BR_RE.sub(" ", text)).strip()


def despace(text: str | None) -> str:
    """조판용 자간 공백을 제거한다.

    `제 출 기 관` → `제출기관`, `과학기술 정보통신부` → `과학기술정보통신부`.

    한글은 단어 사이를 띄우므로 무조건 공백을 지우면 `국세물납증권 매각`처럼
    의미 있는 띄어쓰기까지 붙는다. 그래서 **한 글자씩 떨어진 구간에만** 적용한다.
    """
    s = collapse(text)
    if not s:
        return ""
    # 낱글자가 공백으로만 이어진 덩어리(`법 률 안`)를 찾아 붙인다.
    return re.sub(
        r"(?:(?<=^)|(?<=\s))((?:\S\s){2,}\S)(?=\s|$)",
        lambda m: m.group(1).replace(" ", ""),
        s,
    )


def is_ditto(text: str | None) -> bool:
    return collapse(text) in DITTO_MARKS


def forward_fill(values: list[str], previous: str = "") -> list[str]:
    """`〃`를 바로 위 값으로 채운다."""
    out: list[str] = []
    last = previous
    for v in values:
        cur = collapse(v)
        if is_ditto(cur) or not cur:
            out.append(last)
        else:
            out.append(cur)
            last = cur
    return out
