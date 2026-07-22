"""부처명 → 안정 ID 정규화, 그리고 시계열 비교 가능성 판정.

두 가지 실수를 막는 모듈이다.

1. **집계가 갈라지는 실수** — `기획재정부`와 `재정경제부`를 다른 부처로 세는 것.
2. **집계가 잘못 이어지는 실수** — `산업통상자원부`와 `산업통상부`를 같은
   범위로 보고 시계열을 잇는 것. 개명처럼 보이지만 에너지 기능이 통째로
   기후에너지환경부로 넘어갔다. 모르고 그리면 2025-10-01에 원인 모를 급락이
   생기고, 그걸 정책 변화로 해석하게 된다.

1은 `resolve()`가, 2는 `comparability()`가 맡는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

TABLE_PATH = Path(__file__).parent / "ministries.yaml"

# 계보 kind 중 '같은 범위가 이어진다'고 볼 수 있는 것.
CONTINUOUS_KINDS = {"rename", "elevated"}


@dataclass(frozen=True)
class NameWindow:
    ministry_id: str
    name: str
    valid_from: date | None
    valid_to: date | None

    def covers(self, when: date | None) -> bool:
        if when is None:
            return True
        if self.valid_from and when < self.valid_from:
            return False
        if self.valid_to and when > self.valid_to:
            return False
        return True


@dataclass
class Comparability:
    """두 시점 사이에 그 부처를 그냥 이어도 되는지."""

    comparable: bool
    events: list[dict]

    @property
    def warning(self) -> str | None:
        if self.comparable:
            return None
        parts = []
        for e in self.events:
            kind, on = e.get("kind"), e.get("effective_on")
            what = e.get("what") or e.get("note") or ""
            parts.append(f"{on} {kind}{(' — ' + what) if what else ''}")
        return "; ".join(parts)


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


@lru_cache(maxsize=1)
def _load() -> dict:
    return yaml.safe_load(TABLE_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _windows() -> list[NameWindow]:
    out: list[NameWindow] = []
    for entry in _load()["ministries"]:
        for spec in entry["names"]:
            out.append(
                NameWindow(
                    ministry_id=entry["id"],
                    name=spec["name"],
                    valid_from=_as_date(spec.get("from")),
                    valid_to=_as_date(spec.get("to")),
                )
            )
    return out


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, str]:
    """정식명·약칭 → ministry_id. 공백 제거·정규화된 키를 쓴다."""
    index: dict[str, str] = {}
    for entry in _load()["ministries"]:
        for spec in entry["names"]:
            index[_key(spec["name"])] = entry["id"]
        for alias in entry.get("aliases", []) or []:
            index.setdefault(_key(alias), entry["id"])
    return index


def _key(name: str) -> str:
    """비교용 키. 부처명에는 공백이 없으므로 전부 지운다.

    문서에서 `과학기술\\n정보통신부`, `제 출 기 관`처럼 조판 공백이 섞여 온다.
    """
    return re.sub(r"\s+", "", name or "")


def resolve(name: str, when: date | str | None = None) -> str | None:
    """부처명을 안정 ID로 바꾼다. 모르면 None.

    `when`을 주면 그 시점에 유효한 이름인지도 따진다. 시점을 줬는데 이름이 그
    시점에 존재하지 않으면(예: 2025-07에 `재정경제부`) 그래도 ID는 돌려준다 —
    문서에 그렇게 적혀 있다면 우리 표가 틀렸을 가능성이 있고, 데이터를 버리는
    것보다 `validate_against_observed()`로 잡아내는 편이 낫다.
    """
    key = _key(name)
    if not key:
        return None

    if when is not None:
        at = _as_date(when) if not isinstance(when, date) else when
        exact = [w for w in _windows() if _key(w.name) == key and w.covers(at)]
        if exact:
            return exact[0].ministry_id

    return _alias_index().get(key)


def canonical_name(ministry_id: str, when: date | str | None = None) -> str | None:
    """그 시점에 쓰인 정식 명칭."""
    at = _as_date(when) if when is not None else None
    windows = [w for w in _windows() if w.ministry_id == ministry_id]
    if not windows:
        return None
    for w in windows:
        if w.covers(at):
            return w.name
    return windows[-1].name


def comparability(ministry_id: str, start: date | str, end: date | str) -> Comparability:
    """[start, end] 사이에 이 부처의 집계를 그냥 이어도 되는지 판정한다.

    개명·승격은 이어도 되지만, 기능 이관·분리·흡수가 끼면 비교 대상이 달라진다.
    """
    a, b = _as_date(start), _as_date(end)
    if a > b:
        a, b = b, a

    entry = next((e for e in _load()["ministries"] if e["id"] == ministry_id), None)
    if entry is None:
        return Comparability(comparable=True, events=[])

    breaking = [
        e
        for e in (entry.get("lineage") or [])
        if e.get("kind") not in CONTINUOUS_KINDS and a <= _as_date(e["effective_on"]) <= b
    ]
    return Comparability(comparable=not breaking, events=breaking)


def validate_against_observed(
    observed: list[tuple[str, str]],
) -> list[dict]:
    """수집된 (부처명, 날짜) 쌍이 정규화 표와 어긋나는지 본다.

    표의 시행일은 뉴스로 확인한 값이라 관보와 하루 이틀 다를 수 있고, 문서가
    개편 후에도 옛 이름을 쓰는 경우도 있다. 조용히 넘어가면 잘못된 시점 판정이
    데이터에 굳으므로 전부 보고한다.
    """
    problems: list[dict] = []
    for raw_name, raw_date in observed:
        when = _as_date(raw_date) if raw_date else None
        mid = resolve(raw_name)
        if mid is None:
            problems.append({"issue": "미등록 기관", "name": raw_name, "date": raw_date})
            continue
        if when is None:
            continue
        windows = [w for w in _windows() if w.ministry_id == mid]
        if not any(_key(w.name) == _key(raw_name) for w in windows):
            # 정식명이 아니라 별칭으로 적힌 경우. 별칭에는 유효기간 개념이 없어
            # 시점을 따질 대상이 아니다(`국무총리비서실` → 국무조정실).
            continue
        if not any(_key(w.name) == _key(raw_name) and w.covers(when) for w in windows):
            # 그 이름이 유효한 구간을 그대로 보여준다. 그 시점에 아예 존재하지
            # 않던 이름일 수도 있어(2025년 문서의 `재정경제부`), 다른 이름을
            # '정답'처럼 제시하면 오히려 오해를 부른다.
            same_name = [w for w in windows if _key(w.name) == _key(raw_name)]
            valid = [
                f"{w.valid_from or '~'}~{w.valid_to or '~'}" for w in same_name
            ]
            problems.append(
                {
                    "issue": "시점 불일치",
                    "name": raw_name,
                    "date": raw_date,
                    "ministry_id": mid,
                    "valid_windows": valid,
                    "name_at_that_time": canonical_name(mid, when),
                }
            )
    return problems


def science_tech_ids(include_adjacent: bool = True) -> set[str]:
    data = _load()
    ids = set(data["science_tech_core"])
    if include_adjacent:
        ids |= set(data["science_tech_adjacent"])
    return ids
