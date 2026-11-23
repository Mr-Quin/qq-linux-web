import json

from qq_notify_forward import chatlog
from qq_notify_forward.chatlog import ChatLog


class Clock:
    def __init__(self):
        self.now = 1_000

    def __call__(self):
        self.now += 1
        return self.now


def test_records_counts_and_last_decision(tmp_path):
    log = ChatLog(str(tmp_path / "c.json"), clock=Clock())
    log.record("A", "dropped", "no rule matched")
    log.record("B", "sent", "listed chat")
    log.record("A", "sent", "keyword '@我'")
    entries = log.list()
    assert [e["chat"] for e in entries] == ["A", "B"]
    assert entries[0] | {"last": 0} == {
        "chat": "A",
        "count": 2,
        "verdict": "sent",
        "reason": "keyword '@我'",
        "last": 0,
    }


def test_survives_a_restart(tmp_path):
    path = str(tmp_path / "c.json")
    ChatLog(path).record("A", "sent", "listed chat")
    assert [e["chat"] for e in ChatLog(path).list()] == ["A"]


def test_starts_empty_on_a_broken_file(tmp_path):
    path = tmp_path / "c.json"
    path.write_text("nope")
    assert ChatLog(str(path)).list() == []


def test_drops_the_oldest_chats_past_the_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(chatlog, "MAX_CHATS", 3)
    log = ChatLog(str(tmp_path / "c.json"), clock=Clock())
    for name in "ABCDE":
        log.record(name, "dropped", "no rule matched")
    assert sorted(e["chat"] for e in log.list()) == ["C", "D", "E"]
    assert sorted(json.loads((tmp_path / "c.json").read_text())) == ["C", "D", "E"]
