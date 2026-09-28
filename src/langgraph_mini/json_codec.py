"""도메인 객체(dataclass/Enum/date/datetime)를 JSON에 담기 위한 아주 작은 인코더/디코더.

account/card/billing/orchestration이 전부 같은 문제(dataclass 안에 Enum·date·datetime·
중첩 dataclass가 섞여 있음)를 겪어서 공용으로 뺐다. 이 모듈은 어떤 도메인 패키지도
몰라야 한다 — 반대로 도메인 패키지들이 이 모듈을 가져다 쓴다(의존 방향: 도메인 → 이 모듈).

지원 범위: None/bool/int/float/str, Enum, date/datetime, dataclass(중첩 가능),
dict(키는 항상 문자열이라고 가정 — 지금 코드베이스에서 실제로 그러함), list/tuple
(tuple은 JSON에 없어서 list로 인코딩되고, decode 후에도 list로 남음 — 이 코드베이스에서
튜플의 "튜플임"이 중요한 곳은 없음, 예: transfer_split의 목적지 목록은 언패킹만 하면 됨).
"""

from __future__ import annotations

import importlib
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any


def encode(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return {"__enum__": _qualname(type(value)), "value": value.value}
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, date):
        return {"__date__": value.isoformat()}
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "__dataclass__": _qualname(type(value)),
            "fields": {f.name: encode(getattr(value, f.name)) for f in fields(value)},
        }
    if isinstance(value, dict):
        return {str(key): encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(item) for item in value]
    raise TypeError(f"JSON으로 인코딩할 수 없는 타입: {type(value)!r}")


def decode(value: Any) -> Any:
    if isinstance(value, dict):
        if "__enum__" in value:
            return _resolve(value["__enum__"])(value["value"])
        if "__datetime__" in value:
            return datetime.fromisoformat(value["__datetime__"])
        if "__date__" in value:
            return date.fromisoformat(value["__date__"])
        if "__dataclass__" in value:
            cls = _resolve(value["__dataclass__"])
            return cls(**{k: decode(v) for k, v in value["fields"].items()})
        return {key: decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode(item) for item in value]
    return value


def _qualname(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def _resolve(qualname: str) -> type:
    module_name, _, cls_name = qualname.rpartition(".")
    module = importlib.import_module(module_name)
    return getattr(module, cls_name)
