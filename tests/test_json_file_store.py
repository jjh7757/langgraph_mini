from langgraph_mini.json_file_store import JsonFileStore, JsonListStore


def test_json_file_store_creates_file_with_empty_object(tmp_path):
    path = tmp_path / "records.json"

    store = JsonFileStore(path)

    assert path.read_text(encoding="utf-8") == "{}"
    assert store.load() == {}


def test_json_file_store_round_trips_and_persists(tmp_path):
    path = tmp_path / "records.json"
    store = JsonFileStore(path)
    store.save_all({"a1": {"balance": 1000}})

    # 새 인스턴스로 다시 열어도(=재시작 시뮬레이션) 파일에서 그대로 읽힘
    reopened = JsonFileStore(path)
    assert reopened.load() == {"a1": {"balance": 1000}}


def test_json_list_store_creates_file_with_empty_array(tmp_path):
    path = tmp_path / "records.json"

    store = JsonListStore(path)

    assert path.read_text(encoding="utf-8") == "[]"
    assert store.load() == []


def test_json_list_store_round_trips_and_persists(tmp_path):
    path = tmp_path / "records.json"
    store = JsonListStore(path)
    store.save_all([{"amount": 100}, {"amount": 200}])

    reopened = JsonListStore(path)
    assert reopened.load() == [{"amount": 100}, {"amount": 200}]


def test_json_file_store_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "dir" / "records.json"

    JsonFileStore(path)

    assert path.exists()
