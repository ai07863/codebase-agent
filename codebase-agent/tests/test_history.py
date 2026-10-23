from web.store import ConversationStore


def _store(tmp_path):
    return ConversationStore(str(tmp_path / "history.db"))


def test_create_and_list(tmp_path):
    store = _store(tmp_path)
    cid = store.create("requests", "how does routing work")
    convs = store.list()
    assert len(convs) == 1
    assert convs[0]["id"] == cid
    assert convs[0]["repo"] == "requests"
    assert convs[0]["title"] == "how does routing work"


def test_messages_roundtrip_and_updated_at(tmp_path):
    store = _store(tmp_path)
    cid = store.create("requests", "q")
    before = store.get(cid)["updated_at"]
    store.add_message(cid, "user", "hello")
    store.add_message(cid, "assistant", "hi there")
    conv = store.get(cid)
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["messages"][0]["content"] == "hello"
    assert conv["updated_at"] >= before


def test_list_orders_by_recent(tmp_path):
    store = _store(tmp_path)
    a = store.create("repoA", "first")
    b = store.create("repoB", "second")
    store.add_message(a, "user", "bump a")
    assert store.list()[0]["id"] == a


def test_delete_conversation(tmp_path):
    store = _store(tmp_path)
    cid = store.create("repoA", "q")
    store.add_message(cid, "user", "hi")
    store.delete(cid)
    assert store.get(cid) is None
    assert store.list() == []
    assert store.message_count(cid) == 0


def test_get_missing_returns_none(tmp_path):
    assert _store(tmp_path).get("nope") is None