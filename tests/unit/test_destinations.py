import apprise
import pytest

from qq_notify_forward import destinations


def test_defang_breaks_discord_mass_mentions():
    out = destinations.defang("@everyone and @here")
    assert "@everyone" not in out
    assert "@here" not in out
    assert out.replace("​", "") == "@everyone and @here"


def test_describe_hides_the_secret():
    d = destinations.describe("https://discord.com/api/webhooks/1234/supersecrettoken")
    assert d["service"] == "Discord"
    assert "supersecrettoken" not in d["display"]


def test_describe_drops_the_query_string():
    d = destinations.describe("ntfy://ntfy.sh/topic?token=tk_secret")
    assert "tk_secret" not in d["display"]


def test_describe_invalid():
    assert destinations.describe("nonsense")["service"] == "invalid"


def test_send_posts_title_and_text(webhook):
    notifier = apprise.Apprise()
    notifier.add(f"json://{webhook.url.removeprefix('http://')}/")
    assert destinations.send(notifier, "Chat @everyone", "hello")
    [post] = webhook.posts
    assert post["body"]["title"] == "Chat @​everyone"
    assert post["body"]["message"] == "hello"


def test_send_test_reports_failure(webhook):
    url = f"json://{webhook.url.removeprefix('http://')}/"
    assert destinations.send_test(url)
    webhook.stop()
    assert not destinations.send_test(url)


def test_send_test_rejects_invalid_url():
    with pytest.raises(ValueError):
        destinations.send_test("nonsense")
