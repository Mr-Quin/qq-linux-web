import pytest

from qq_notify_forward.rules import decide
from qq_notify_forward.settings import Settings

RULES = Settings(
    {
        "forward": {"chats": ["Family"], "keywords": ["@我"]},
        "ignore": {"chats": ["Noisy Group"], "keywords": ["广告"]},
    }
)


@pytest.mark.parametrize(
    ("chat", "body", "send", "reason"),
    [
        ("Family", "广告 spam", False, "ignored keyword '广告'"),
        ("Noisy Group", "[有人@我] look", True, "keyword '@我'"),
        ("Noisy Group", "chatter", False, "ignored chat"),
        ("Family", "dinner?", True, "listed chat"),
        ("Someone", "hello", False, "no rule matched"),
        ("@我 fan club", "hello", True, "keyword '@我'"),
    ],
)
def test_first_matching_rule_wins(chat, body, send, reason):
    assert decide(RULES, chat, body) == (send, reason)


def test_star_forwards_every_chat_not_ignored():
    rules = Settings({"forward": {"chats": ["*"]}, "ignore": {"chats": ["Muted"]}})
    assert decide(rules, "Anyone", "hi") == (True, "all chats")
    assert decide(rules, "Muted", "hi") == (False, "ignored chat")


def test_default_settings_forward_only_mentions():
    rules = Settings({"forward": {"keywords": ["@我"]}})
    assert decide(rules, "Group", "[有人@我]")[0]
    assert not decide(rules, "Group", "hello")[0]
