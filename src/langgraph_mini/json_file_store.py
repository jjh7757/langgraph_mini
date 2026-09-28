"""파일 하나에 레코드 전체를 통째로 읽고 쓰는 아주 단순한 저장소.

트랜잭션/락 없음 — save할 때마다 전체를 다시 씀. 지금 규모(단일 프로세스, 로컬 파일)에서는
문제 없지만, Memory 구현체와 동일한 수준으로 동시성은 보장하지 않는다(여러 프로세스가
같은 파일에 동시에 쓰면 마지막에 쓴 쪽만 남음).

두 가지 모양을 지원:
    JsonFileStore     {id: 레코드} — Account/Card/Bill처럼 고유 id로 덮어쓰는 엔티티
    JsonListStore     [레코드, ...] — Transaction처럼 id 없이 append만 하는 엔티티
"""

import json
from pathlib import Path
from typing import Any

from . import json_codec as codec


class JsonFileStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("{}", encoding="utf-8")

    def load(self) -> dict[str, Any]:
        raw = json.loads(self._path.read_text(encoding="utf-8") or "{}")
        return {key: codec.decode(value) for key, value in raw.items()}

    def save_all(self, records: dict[str, Any]) -> None:
        raw = {key: codec.encode(value) for key, value in records.items()}
        self._path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")


class JsonListStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("[]", encoding="utf-8")

    def load(self) -> list[Any]:
        raw = json.loads(self._path.read_text(encoding="utf-8") or "[]")
        return [codec.decode(item) for item in raw]

    def save_all(self, records: list[Any]) -> None:
        raw = [codec.encode(item) for item in records]
        self._path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
