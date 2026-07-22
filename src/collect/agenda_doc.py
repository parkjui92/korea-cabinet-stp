"""국무회의 `의사일정` 문서에서 안건 전수를 뽑는다.

브리핑 본문도, 결과 보도자료도 `심의·의결된 안건 중 일부 내용은 다음과 같습니다`
라며 주요 안건만 싣는다(제30회: 27건 의결 중 6건). **안건 전수를 담은 유일한
출처가 의사일정 첨부다.**

문서 구조(제30회 기준, kordoc `--format json`의 blocks):

    [0] table  머리표 — 일시·장소·안건 유형별 건수
    [1] para   `※ 집중토의 : 1건`
    [2] table  집중토의 안건 (안건명 | 소관)
    [3] para   `○ 부 처 보 고 : 5건`
    [4] table  부처보고 안건
    [5] para   `※ 집중토의 : 2건`
    [6] table  집중토의 안건 (협조요청)
    [7] para   `○ 차관회의 심의안건 : 25건 / 국무회의 즉석안건 : 2건`
    [8] table  **의안 표** — 의안번호·제출월일·제출기관·의안명·차관회의·국무회의

의안 표는 유형 구분행(`법 률 안 ( 3건 )`)으로 구획되고, 반복되는 값은 `〃`로
줄여 쓴다.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..normalize.textnorm import DITTO_MARKS, collapse, despace, is_ditto

# 의안 유형 표시. 두 자리에서 서로 다른 모양으로 나온다.
#   표 안 구분행 : `법 률 안 ( 3건 )`
#   표 앞 문단   : `○ 법 률 공 포 안 : 5건`
# 자간·괄호·콜론이 제각각이라 셋 다 선택적으로 받는다.
# 긴 이름을 먼저 둬야 `법률공포안`이 `법률안`으로 잘리지 않는다.
_CATEGORY_RE = re.compile(
    r"^(법률공포안|법률안|대통령령안|총리령안|일반안건|일반안|보고안건)\s*[(:：]?\s*(\d+)\s*건"
)

# 의결되지 않는 유형. 의결 건수를 셀 때 빼야 한다.
# `보고안건`은 차관회의 결과가 `원안접수`로 찍히며 국무회의에 보고만 된다.
# 이걸 일반안건으로 묶으면 의결 건수가 부풀려진다(실측: 2025-033에서 +1).
NON_RESOLVED_CATEGORIES = {"보고안건"}

# 안건 유형 전체 어휘. 수집된 64개 의사일정에서 실측한 값이다.
# (집중토의·부처보고·협조사항은 의안이 아니라 별도 표의 보고·토의 섹션이다)
KNOWN_CATEGORIES = {
    "법률공포안",
    "법률안",
    "대통령령안",
    "총리령안",
    "일반안건",
    "보고안건",
}
# `○ 부 처 보 고 : 5건` / `※ 집중토의 : 1건` — 콜론이 전각(：)으로 나오기도 한다.
_SECTION_RE = re.compile(r"^[○※]\s*(.+?)\s*[:：]\s*(\d+)\s*건")

# 보고·토의 표의 제목 칸. `1. 제목` — 항목이 하나뿐이면 번호를 생략하기도 한다.
_ORDER_PREFIX_RE = re.compile(r"^(\d+)\.\s*(.*)$")
# 소관 칸. `(성평등가족부)` — 항상 괄호로 감싸진다(실측 146행 전량 확인).
_PAREN_RE = re.compile(r"^\((.+)\)$")
# `국무총리(공정거래위원회)` / `국무총리직무대행(고용노동부)`
# 처·위원회는 독자 제출권이 없어 총리 명의로 올라온다. **실소관은 괄호 안**이다.
_DELEGATED_RE = re.compile(r"^국무총리(?:직무대행)?\((.+?)\)$")

# `행정안전부(교육부)` 같은 형태는 뜻이 반대다. 행안부가 소관이고 괄호 안은
# 그 직제령이 적용되는 **대상** 부처다. 괄호를 실소관으로 읽으면 직제 개정이
# 전부 대상 부처 실적으로 잘못 집계된다.
_SUBJECT_RE = re.compile(r"^(.+?)\((.+?)\)$")
_DATE_RE = re.compile(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})")


@dataclass
class AgendaItem:
    """심의·의결 의안 한 건."""

    bill_no: str
    category: str  # 법률안 · 대통령령안 · 일반안건 …
    title: str
    submitter: str  # 실소관
    subject_org: str  # 직제령 등에서 괄호로 표기된 대상 기관 (없으면 빈 문자열)
    submitter_raw: str  # 문서 원문 표기
    submitted_on: str | None  # ISO
    vice_result: str  # 차관회의 결과
    cabinet_result: str  # 국무회의 결과


SECTION_DISCUSSION = "집중토의"
SECTION_REPORT = "부처보고"
SECTION_COOPERATION = "협조사항"


@dataclass
class ReportItem:
    """보고·토의 안건 한 건.

    의안 표(AgendaItem)가 의결 결과를 담는다면, 이쪽은 **그 자리에서 어떤
    주제가 다뤄졌는지**를 담는다. 의결까지 가지 않는 정책 토의·보고가 많아
    의안 표만으로는 안 잡히는 의제가 여기 있다(예: 하반기 경제성장전략 보고는
    일반안건이 아니라 부처보고로만 잡힌다).
    """

    section: str  # 집중토의 · 부처보고 · 협조사항
    order: int
    title: str
    ministry_raw: str  # 원문 그대로 (예: `관계부처`처럼 특정 부처가 아닐 수 있음)


@dataclass
class AgendaDoc:
    session_title: str
    held_on: str | None
    venue: str
    declared_counts: dict[str, int] = field(default_factory=dict)
    items: list[AgendaItem] = field(default_factory=list)
    reports: list[ReportItem] = field(default_factory=list)


# ----------------------------------------------------------------------
def parse_with_kordoc(path: Path, kordoc: str = "kordoc") -> dict:
    """kordoc CLI로 문서를 구조화 JSON으로 읽는다.

    kordoc은 MCP 서버이자 CLI다. 주간 자동화가 스크립트에서 돌아야 하므로
    MCP가 아니라 CLI를 쓴다.

    `-o -`는 stdout으로 나가지 않고 **`-`라는 이름의 파일을 만든다.** 조용히
    빈 stdout을 돌려주므로 임시 파일로 받는다.
    """
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "doc.json"
        result = subprocess.run(
            [kordoc, str(path), "--format", "json", "--silent", "-o", str(out)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"kordoc 실패({result.returncode}): {result.stderr[:400]}")
        if not out.exists():
            raise RuntimeError(f"kordoc 출력 없음: {result.stdout[:200]} {result.stderr[:200]}")
        return json.loads(out.read_text(encoding="utf-8"))


def _cell_texts(row: list[dict]) -> list[str]:
    """행을 논리 칸 목록으로 바꾼다. colSpan을 따라간다.

    kordoc은 병합 셀을 하나로 합치지 않는다 — 첫 물리 칸에 값을 넣고 나머지
    (colSpan-1)개 물리 칸을 빈 문자열로 채운다. 6칸짜리 표가 물리적으로는
    11칸(colSpans=[2,1,2,1,2,1,1,3,1,1,1])으로 나오는 문서가 실제로 있다
    (2023-037). 고정 인덱스로 읽으면 제출월일 칸에 있어야 할 날짜가 제출기관
    칸으로 밀려 들어간다. colSpan만큼 건너뛰어 논리 칸을 복원해야 한다.

    2025-2026 문서는 colSpan이 대부분 1이라 이 함수는 그 경우 항등 함수와
    같다 — 최근 데이터가 우연히 안 걸렸을 뿐 항상 옳은 일반형이다.
    """
    texts: list[str] = []
    skip_until = 0
    for i, cell in enumerate(row):
        if i < skip_until:
            continue
        texts.append(collapse(cell.get("text")))
        skip_until = i + cell.get("colSpan", 1)
    return texts


def _is_spanning_label(row: list[dict], total_cols: int) -> bool:
    """유형 구분행처럼 한 칸이 표 전체를 가로지르는 행인지."""
    return len(row) == 1 or (row and row[0].get("colSpan", 1) >= total_cols)


def _to_iso(raw: str) -> str | None:
    m = _DATE_RE.search(raw)
    if not m:
        return None
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def _split_submitter(raw: str) -> tuple[str, str, str]:
    """제출기관 원문에서 (실소관, 대상기관, 원문)을 낸다.

    셀 폭에 맞춰 `과학기술\\n정보통신부`, `국무총리 (원자력안전 위원회)`처럼
    기관명 한가운데서 줄이 바뀐다. 우리나라 부처·처·청·위원회 이름에는 공백이
    없으므로 이 필드에 한해 공백을 전부 지우는 것이 안전하다.

    괄호는 두 가지 뜻으로 쓰인다.
      `국무총리(원자력안전위원회)` → 총리는 형식적 제출자, **실소관은 괄호 안**
      `행정안전부(교육부)`         → **행안부가 소관**, 괄호는 직제령의 대상
    """
    text = collapse(raw)
    # 셀 병합 잔재로 반복기호가 값에 붙어 오는 경우가 있다(`〃국무총리(행안부)`).
    packed = re.sub(r"\s+", "", text).lstrip("".join(DITTO_MARKS))

    m = _DELEGATED_RE.match(packed)
    if m:
        return m.group(1), "", text

    m = _SUBJECT_RE.match(packed)
    if m:
        return m.group(1), m.group(2), text

    return packed, "", text


def resolve_ditto(cell: str, previous: str) -> str:
    """`〃`나 빈 칸이면 바로 위 값을 잇는다. 열 단위로 부른다.

    제출월일·제출기관처럼 **반드시 값이 있어야 하는** 열에 쓴다.
    """
    value = collapse(cell)
    return previous if (not value or is_ditto(value)) else value


def _carry_ditto_only(cell: str, previous: str) -> str:
    """`〃`만 승계하고 빈 칸은 빈 채로 둔다.

    의결결과 열에 쓴다. 즉석안건은 차관회의를 거치지 않아 칸이 실제로 비어 있다
    (제30회 1211·1212). 빈 칸을 위 값으로 채우면 없는 의결을 지어내는 셈이다.
    """
    value = collapse(cell)
    if not value:
        return ""
    return previous if is_ditto(value) else value


# ----------------------------------------------------------------------
def parse_bill_table(
    block: dict, default_category: str = "", carry: dict | None = None
) -> list[AgendaItem]:
    """의안 표 하나를 안건 목록으로 바꾼다.

    `default_category`는 표 앞 문단이 유형을 지정한 경우에 쓴다
    (`○ 법 률 공 포 안 : 16건` → 그 표 전체가 법률공포안). 표 안에 유형
    구분행이 있으면 그쪽이 이긴다.

    `carry`는 표를 넘나드는 `〃` 승계 상태다. 한 회의의 의안 표가 여러 개로
    쪼개질 때 첫 행이 `〃`로 시작할 수 있다.
    """
    table = block["table"]
    cols = table["cols"]
    rows = table["cells"]

    items: list[AgendaItem] = []
    category = default_category
    # 〃 채우기는 열별로 독립이다.
    state = carry if carry is not None else {}
    last_date = state.get("date", "")
    last_submitter = state.get("submitter", "")
    last_vice = state.get("vice", "")
    last_cabinet = state.get("cabinet", "")

    for row in rows:
        texts = _cell_texts(row)
        if not texts:
            continue

        # 유형 구분행 — 이후 행들의 category가 된다.
        if _is_spanning_label(row, cols):
            m = _CATEGORY_RE.match(despace(texts[0]))
            if m:
                category = "일반안건" if m.group(1) == "일반안" else m.group(1)
            continue

        # 헤더행 건너뛰기
        if despace(texts[0]) in {"의안번호", "의안번호제출월일"}:
            continue

        # 의안번호가 숫자가 아니면 데이터행이 아니다.
        bill_no = collapse(texts[0])
        if not bill_no.isdigit():
            continue

        # `〃`는 열마다 독립적으로 바로 위 값을 승계한다.
        date_val = resolve_ditto(texts[1] if len(texts) > 1 else "", last_date)
        last_date = date_val
        sub_raw = resolve_ditto(texts[2] if len(texts) > 2 else "", last_submitter)
        last_submitter = sub_raw

        submitter, subject_org, submitter_raw = _split_submitter(sub_raw)

        # 의결결과도 반복 기호를 쓴다. 다만 즉석안건처럼 애초에 빈 칸인 경우가
        # 있어, 빈 칸을 위 값으로 채우면 없는 의결을 지어내게 된다.
        # 여기서는 `〃`만 승계하고 빈 칸은 빈 채로 둔다.
        vice = _carry_ditto_only(texts[4] if len(texts) > 4 else "", last_vice)
        cabinet = _carry_ditto_only(texts[5] if len(texts) > 5 else "", last_cabinet)
        if vice:
            last_vice = vice
        if cabinet:
            last_cabinet = cabinet

        items.append(
            AgendaItem(
                bill_no=bill_no,
                category=category,
                title=collapse(texts[3]) if len(texts) > 3 else "",
                submitter=submitter,
                subject_org=subject_org,
                submitter_raw=submitter_raw,
                submitted_on=_to_iso(date_val),
                vice_result=vice,
                cabinet_result=cabinet,
            )
        )

    if carry is not None:
        carry.update(
            date=last_date, submitter=last_submitter, vice=last_vice, cabinet=last_cabinet
        )
    return items


def _is_bill_table(block: dict) -> bool:
    """의안 표인지. 머리행에 `의안번호`가 있는 6열짜리."""
    if block.get("type") != "table":
        return False
    table = block["table"]
    if table["cols"] < 5 or not table["cells"]:
        return False
    head = " ".join(despace(collapse(c.get("text"))) for c in table["cells"][0])
    return "의안번호" in head or "의안명" in head


def _label_category(text: str) -> str:
    """구획 문단이 유형을 지정하는지 본다.

    `○ 법 률 공 포 안 : 16건` → 법률공포안
    `○ 법 률 공 포 안`        → 법률공포안  (hwpx본은 건수를 안 붙인다)
    `○ 차관회의 심의안건 : 13건` → (유형 아님, 절차 구분)
    """
    body = despace(collapse(text)).lstrip("○※-·").strip()
    m = _CATEGORY_RE.match(body)
    if m:
        return "일반안건" if m.group(1) == "일반안" else m.group(1)

    # 건수 없이 유형명만 있는 형태. 라벨 전체가 유형명일 때만 인정해
    # 본문 문장이 우연히 걸리는 것을 막는다.
    bare = re.sub(r"\s+", "", body)
    if bare in KNOWN_CATEGORIES:
        return bare
    if bare == "일반안":
        return "일반안건"
    return ""


def parse_agenda_items(doc: dict) -> list[AgendaItem]:
    """문서 전체에서 안건을 모은다.

    의안 표는 **하나가 아니다.** 회차에 따라 절차별로 표가 쪼개진다.

        ○ 법 률 공 포 안 : 16건      → 표 (16건, 전부 법률공포안)
        ○ 차관회의 심의안건 : 13건   → 표 (13건, 안에 유형 구분행)

    가장 큰 표 하나만 읽으면 나머지가 조용히 사라진다. 실측에서 제31회는
    29건 중 16건만, 제26회는 39건 중 23건만 잡혔다.
    """
    items: list[AgendaItem] = []
    seen: set[str] = set()
    pending_category = ""
    carry: dict = {}

    for block in doc.get("blocks", []):
        if block.get("type") != "table":
            label = _label_category(block.get("text", ""))
            if label:
                pending_category = label
            elif collapse(block.get("text", "")).startswith(("○", "※")):
                # 절차 구분(차관회의 심의안건 등) — 유형은 표 안에서 정해진다.
                pending_category = ""
            continue

        if not _is_bill_table(block):
            continue

        for item in parse_bill_table(block, default_category=pending_category, carry=carry):
            if item.bill_no in seen:
                continue
            seen.add(item.bill_no)
            items.append(item)

    return items


def _label_declaration(text: str) -> tuple[str, int] | None:
    """`○ 법 률 공 포 안 : 3건` / `법 률 안 ( 2건 )` → (유형, 건수)."""
    m = _CATEGORY_RE.match(despace(collapse(text)).lstrip("○※-·").strip())
    if not m:
        return None
    key = "일반안건" if m.group(1) == "일반안" else m.group(1)
    return key, int(m.group(2))


def declared_counts(doc: dict) -> dict[str, int]:
    """문서가 스스로 밝힌 유형별 선언 건수.

    `parse_agenda_items`가 category를 정할 때 쓰는 **우선순위를 그대로** 따른다.
    같은 기준으로 세지 않으면 비교 자체가 무의미하다.

      · 표지 요약표(일시·장소와 함께 건수를 다시 적는 표)는 건너뛴다.
        본문과 같은 숫자를 중복 선언한다(2018-054: 법률공포안 103건이 표지·
        본문에 각각 등장).
      · 한 의안 표에 대해 **표 안 구분행이 있으면 그것만** 센다. 표 앞 문단
        라벨은 같은 선언의 다른 표현일 뿐이라, 둘 다 더하면 정확히 2배가 된다
        (2024-042: 법률공포안이 문단 `○ 법 률 공 포 안 : 3건`과 구분행
        `법 률 공 포 안 (3건 )`에 중복 등장 → 6건으로 부풀려짐).
      · 구분행이 없는 표에서만 앞 문단 라벨을 쓴다(hwpx본이 이 형태다).

    같은 유형이 서로 다른 의안 표에 나뉘어 나오면 합산한다 — 별개 묶음이다
    (2024-042: 일반안건이 두 표에 3건 + 10건 = 13건).
    """
    counts: dict[str, int] = {}
    pending: tuple[str, int] | None = None

    for block in doc.get("blocks", []):
        if block.get("type") != "table":
            decl = _label_declaration(block.get("text", ""))
            if decl:
                pending = decl
            elif collapse(block.get("text", "")).startswith(("○", "※")):
                # 절차 구분(차관회의 심의안건 등) — 유형 선언이 아니다.
                pending = None
            continue

        if not _is_bill_table(block):
            continue

        table = block["table"]
        dividers: list[tuple[str, int]] = []
        for row in table["cells"]:
            texts = _cell_texts(row)
            if texts and _is_spanning_label(row, table["cols"]):
                decl = _label_declaration(texts[0])
                if decl:
                    dividers.append(decl)

        for key, num in dividers or ([pending] if pending else []):
            counts[key] = counts.get(key, 0) + num
        pending = None

    return counts


def _section_label(text: str) -> tuple[str, int] | None:
    """구획 문단이 보고·토의 섹션을 여는지 본다.

    `○ 법 률 공 포 안 : 16건`처럼 의안 유형과 같은 모양이라, KNOWN_CATEGORIES에
    속하면 의안 표 라벨이지 보고·토의 섹션이 아니다. 여기서 걸러야 한다
    (놓치면 의안 표를 2번짜리 보고 표로 잘못 읽는다).
    """
    raw = collapse(text)
    packed = re.sub(r"\s+", "", raw)
    if "차관회의" in packed or "즉석안건" in packed:
        return None  # 의안 표 소속 절차 라벨

    m = _SECTION_RE.match(despace(raw))
    if not m:
        return None
    section = re.sub(r"\s+", "", m.group(1))
    if section in KNOWN_CATEGORIES or section == "일반안":
        return None
    return section, int(m.group(2))


def _is_report_table(block: dict) -> bool:
    """보고·토의 표인지. 2열이고 의안 표(6열)가 아니다."""
    if block.get("type") != "table":
        return False
    table = block["table"]
    return table["cols"] == 2 and bool(table["cells"])


def parse_report_table(block: dict, section: str) -> list[ReportItem]:
    """보고·토의 표 하나를 항목 목록으로 바꾼다."""
    items: list[ReportItem] = []
    for row in block["table"]["cells"]:
        texts = _cell_texts(row)
        title_cell = texts[0] if texts else ""
        if not title_cell:
            continue  # 빈 머리행

        m = _ORDER_PREFIX_RE.match(title_cell)
        order, title = (int(m.group(1)), m.group(2)) if m else (len(items) + 1, title_cell)

        ministry_cell = texts[1] if len(texts) > 1 else ""
        pm = _PAREN_RE.match(ministry_cell)
        ministry_raw = pm.group(1) if pm else ministry_cell

        items.append(
            ReportItem(section=section, order=order, title=title, ministry_raw=ministry_raw)
        )
    return items


def parse_report_items(doc: dict) -> list[ReportItem]:
    """문서 전체에서 부처보고·집중토의·협조사항을 모은다.

    이 안건들은 의안 표에 없다. 대통령이 그 자리에서 무슨 보고를 받고 무슨
    토의를 했는지는 여기서만 잡힌다 — 예를 들어 「2026년 하반기 경제성장전략」
    보고는 의결 절차를 거치지 않아 AgendaItem에는 나타나지 않는다.
    """
    items: list[ReportItem] = []
    pending: tuple[str, int] | None = None

    for block in doc.get("blocks", []):
        if block.get("type") != "table":
            label = _section_label(block.get("text", ""))
            if label is not None:
                pending = label
            continue

        if pending is None or not _is_report_table(block):
            continue

        section, declared = pending
        items.extend(parse_report_table(block, section))
        pending = None  # 표를 하나 소비했으니 다음 라벨을 기다린다

    return items
