"""extract_reply_text — AIMessage.content가 str이 아니라 Gemini의 다중 파트 리스트로 올 때도
CLI/웹 화면에 "[object Object]"나 파이썬 repr이 새어나가지 않도록 텍스트만 뽑아내는지 검증.
실제로 프로덕션 챗봇에서 재현된 버그(콘텐츠가 [{"type": "text", "text": ...}] 형태로 옴)."""

from langgraph_mini.agent.graph import extract_reply_text


def test_plain_string_passes_through():
    assert extract_reply_text("안녕하세요") == "안녕하세요"


def test_none_becomes_empty_string():
    assert extract_reply_text(None) == ""


def test_list_of_text_parts_joins_text_only():
    content = [{"type": "text", "text": "안녕하세요"}, {"type": "text", "text": " 반갑습니다"}]
    assert extract_reply_text(content) == "안녕하세요 반갑습니다"


def test_list_mixing_strings_and_dicts():
    content = ["안녕", {"type": "text", "text": "하세요"}]
    assert extract_reply_text(content) == "안녕하세요"


def test_list_with_non_text_parts_are_skipped():
    content = [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "결과입니다"}]
    assert extract_reply_text(content) == "결과입니다"


def test_list_with_no_text_parts_is_empty_string():
    assert extract_reply_text([{"type": "thinking", "thinking": "..."}]) == ""
