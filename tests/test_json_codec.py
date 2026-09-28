from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from langgraph_mini.json_codec import decode, encode


class _Color(Enum):
    RED = "빨강"
    BLUE = "파랑"


@dataclass
class _Inner:
    value: int


@dataclass
class _Outer:
    name: str
    color: _Color
    when: datetime
    day: date
    inner: _Inner
    tags: list[str]
    meta: dict


def test_primitives_round_trip():
    for value in [None, True, False, 1, 1.5, "text", ""]:
        assert decode(encode(value)) == value


def test_enum_round_trips_to_same_member():
    assert decode(encode(_Color.RED)) is _Color.RED


def test_datetime_round_trips():
    now = datetime(2026, 1, 2, 3, 4, 5)
    assert decode(encode(now)) == now


def test_date_round_trips():
    day = date(2026, 1, 2)
    assert decode(encode(day)) == day


def test_nested_dataclass_round_trips():
    outer = _Outer(
        name="테스트",
        color=_Color.BLUE,
        when=datetime(2026, 1, 1),
        day=date(2026, 1, 1),
        inner=_Inner(value=42),
        tags=["a", "b"],
        meta={"k": 1},
    )

    result = decode(encode(outer))

    assert result == outer
    assert isinstance(result, _Outer)
    assert isinstance(result.inner, _Inner)
    assert result.color is _Color.BLUE


def test_list_and_dict_round_trip():
    value = {"items": [1, 2, {"nested": _Color.RED}]}

    result = decode(encode(value))

    assert result["items"][:2] == [1, 2]
    assert result["items"][2]["nested"] is _Color.RED


def test_encoded_value_is_json_serializable():
    import json

    outer = _Outer(
        name="테스트",
        color=_Color.BLUE,
        when=datetime(2026, 1, 1),
        day=date(2026, 1, 1),
        inner=_Inner(value=42),
        tags=["a", "b"],
        meta={"k": 1},
    )

    # encode 결과가 실제로 json.dumps 가능한지(=순수 dict/list/primitive인지) 확인
    json.dumps(encode(outer), ensure_ascii=False)
