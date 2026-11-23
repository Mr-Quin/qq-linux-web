import json
import os
import threading
import urllib.error
import urllib.request

import pytest

from qq_notify_forward.api import Api, make_server
from qq_notify_forward.chatlog import ChatLog
from qq_notify_forward.settings import SettingsFile

SECRET_URL = "https://discord.com/api/webhooks/1234/supersecrettoken"


@pytest.fixture
def client(tmp_path, write_json, webhook):
    path = write_json("s.json", {"destinations": [SECRET_URL, f"json://{webhook.url.removeprefix('http://')}/"]})
    chats = ChatLog(str(tmp_path / "c.json"))
    chats.record("Noisy Group", "dropped", "ignored chat")
    server = make_server(Api(SettingsFile(str(path)), chats), "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def call(method, path, body=None, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}{path}",
            method=method,
            data=data,
            headers={"Content-Type": content_type} if data is not None else {},
        )
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def call_json(*args, **kwargs):
        status, raw = call(*args, **kwargs)
        return status, json.loads(raw)

    call_json.raw = call
    call_json.settings_path = path
    yield call_json
    server.shutdown()
    server.server_close()


def test_serves_the_page(client):
    status, raw = client.raw("GET", "/")
    assert status == 200
    assert b"QQ notification forwarding" in raw


def test_state_hides_secrets_and_lists_chats(client):
    status, state = client("GET", "/api/state")
    assert status == 200
    assert "supersecrettoken" not in json.dumps(state)
    assert [d["id"] for d in state["destinations"]] == [0, 1]
    assert [c["chat"] for c in state["chats"]] == ["Noisy Group"]


def test_save_keeps_saved_secrets_and_adds_new_urls(client):
    _, state = client("GET", "/api/state")
    status, saved = client(
        "PUT",
        "/api/settings",
        {
            "version": state["version"],
            "destinations": [{"id": 0}, {"url": "ntfy://ntfy.sh/qq"}],
            "forward": {"chats": ["Family"], "keywords": []},
            "ignore": {"chats": [], "keywords": []},
        },
    )
    assert status == 200
    assert saved["forward"]["chats"] == ["Family"]
    on_disk = json.loads(client.settings_path.read_text())
    assert on_disk["destinations"] == [SECRET_URL, "ntfy://ntfy.sh/qq"]


def test_stale_save_is_a_conflict(client):
    _, state = client("GET", "/api/state")
    body = {"version": state["version"], "destinations": []}
    assert client("PUT", "/api/settings", body)[0] == 200
    assert client("PUT", "/api/settings", body)[0] == 409


def test_invalid_new_url_is_rejected(client):
    _, state = client("GET", "/api/state")
    status, err = client("PUT", "/api/settings", {"version": state["version"], "destinations": [{"url": "nonsense"}]})
    assert status == 400
    assert "not a valid Apprise URL" in err["error"]


def test_unknown_destination_id_is_rejected(client):
    _, state = client("GET", "/api/state")
    assert client("PUT", "/api/settings", {"version": state["version"], "destinations": [{"id": 9}]})[0] == 400


def test_form_posts_are_refused(client):
    status, _ = client("PUT", "/api/settings", b"x=1", content_type="application/x-www-form-urlencoded")
    assert status == 415


def test_check_uses_the_draft_rules(client):
    status, r = client(
        "POST",
        "/api/check",
        {
            "chat": "Noisy Group",
            "text": "[有人@我]",
            "forward": {"keywords": ["@我"]},
            "ignore": {"chats": ["Noisy Group"]},
        },
    )
    assert (status, r) == (200, {"send": True, "reason": "keyword '@我'"})


def test_test_button_reaches_a_saved_destination(client, webhook):
    assert client("POST", "/api/test", {"id": 1}) == (200, {"ok": True})
    assert webhook.posts[0]["body"]["message"] == "Test message from the QQ settings page."


def test_test_button_takes_an_unsaved_url(client, webhook):
    url = f"json://{webhook.url.removeprefix('http://')}/"
    assert client("POST", "/api/test", {"url": url}) == (200, {"ok": True})


def test_unknown_routes(client):
    assert client("GET", "/api/nope")[0] == 404
    assert client("POST", "/api/settings", {})[0] == 404


def test_stale_save_never_resolves_ids_against_newer_settings(client, write_json):
    _, state = client("GET", "/api/state")
    write_json("s.json", {"destinations": ["json://127.0.0.1:2/"]})
    path = client.settings_path
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    status, _ = client("PUT", "/api/settings", {"version": state["version"], "destinations": [{"id": 1}]})
    assert status == 409
