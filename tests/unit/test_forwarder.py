import logging

import pytest

from qq_notify_forward.chatlog import ChatLog
from qq_notify_forward.forwarder import Forwarder
from qq_notify_forward.settings import SettingsFile


@pytest.fixture
def make_forwarder(tmp_path, write_json):
    def make(settings):
        path = write_json("s.json", settings)
        return Forwarder(SettingsFile(str(path)), ChatLog(str(tmp_path / "c.json")))

    return make


def hook_url(webhook):
    return f"json://{webhook.url.removeprefix('http://')}/"


def test_sends_matching_notifications(make_forwarder, webhook):
    f = make_forwarder({"destinations": [hook_url(webhook)], "forward": {"chats": ["Family"]}})
    assert f.handle("QQ", "Family", "dinner?") == "sent"
    assert f.handle("QQ", "Other", "hi") == "dropped"
    assert [p["body"]["message"] for p in webhook.posts] == ["dinner?"]


def test_ignores_other_apps(make_forwarder, webhook):
    f = make_forwarder({"destinations": [hook_url(webhook)], "forward": {"chats": ["*"]}})
    assert f.handle("Firefox", "Family", "hi") is None
    assert webhook.posts == []
    assert f.chatlog.list() == []


def test_matching_without_destinations_is_dropped(make_forwarder):
    f = make_forwarder({"forward": {"chats": ["*"]}})
    assert f.handle("QQ", "Family", "hi") == "dropped"
    assert f.chatlog.list()[0]["reason"] == "all chats, but no destinations are set"


def test_unreachable_destination_is_a_send_failure(make_forwarder):
    f = make_forwarder({"destinations": ["json://127.0.0.1:1/"], "forward": {"chats": ["*"]}})
    assert f.handle("QQ", "Family", "hi") == "send failed"


def test_logs_the_decision(make_forwarder, caplog):
    caplog.set_level(logging.INFO)
    f = make_forwarder({"ignore": {"chats": ["Noisy Group"]}})
    f.handle("QQ", "Noisy Group", "chatter")
    assert "dropped: chat 'Noisy Group', ignored chat" in caplog.text
