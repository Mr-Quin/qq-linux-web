import json
import os
import stat

import pytest

from qq_notify_forward.settings import DEFAULT_SETTINGS, Conflict, Settings, SettingsFile, normalize


def test_normalize_strips_dedupes_and_fills_sections():
    assert normalize({"forward": {"chats": [" A ", "A", "", "B"]}}) == {
        "destinations": [],
        "forward": {"chats": ["A", "B"], "keywords": []},
        "ignore": {"chats": [], "keywords": []},
    }


@pytest.mark.parametrize(
    "raw",
    [[], {"destinations": "json://x"}, {"forward": []}, {"ignore": {"chats": [1]}}],
)
def test_normalize_rejects_wrong_shapes(raw):
    with pytest.raises(ValueError):
        normalize(raw)


def test_invalid_destination_is_skipped_not_fatal():
    s = Settings({"destinations": ["json://127.0.0.1:1/", "nonsense"]})
    assert len(s.notifier) == 1
    assert s.raw["destinations"] == ["json://127.0.0.1:1/", "nonsense"]


def test_creates_a_private_default_file(tmp_path):
    path = tmp_path / "s.json"
    SettingsFile(str(path))
    assert json.loads(path.read_text()) == DEFAULT_SETTINGS
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def bump_mtime(path):
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))


def test_reloads_when_the_file_changes(write_json):
    path = write_json("s.json", {"forward": {"chats": ["A"]}})
    f = SettingsFile(str(path))
    assert f.get()[0].forward_chats == {"A"}
    write_json("s.json", {"forward": {"chats": ["B"]}})
    bump_mtime(path)
    assert f.get()[0].forward_chats == {"B"}


def test_broken_file_keeps_the_last_good_settings(write_json, caplog):
    path = write_json("s.json", {"forward": {"chats": ["A"]}})
    f = SettingsFile(str(path))
    f.get()
    path.write_text("{ not json")
    bump_mtime(path)
    assert f.get()[0].forward_chats == {"A"}
    assert "is invalid, keeping the previous settings" in caplog.text


def test_save_writes_and_returns_the_new_version(write_json):
    path = write_json("s.json", {})
    f = SettingsFile(str(path))
    _, version = f.get()
    settings, new_version = f.save({"ignore": {"chats": ["X"]}}, version)
    assert settings.ignore_chats == {"X"}
    assert new_version != version
    assert json.loads(path.read_text())["ignore"]["chats"] == ["X"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_save_over_a_newer_edit_is_refused(write_json):
    path = write_json("s.json", {})
    f = SettingsFile(str(path))
    _, version = f.get()
    write_json("s.json", {"forward": {"chats": ["edited by hand"]}})
    bump_mtime(path)
    f.get()
    with pytest.raises(Conflict):
        f.save({}, version)
    assert "edited by hand" in path.read_text()


def test_save_rejects_invalid_settings_without_writing(write_json):
    path = write_json("s.json", {"forward": {"chats": ["A"]}})
    f = SettingsFile(str(path))
    _, version = f.get()
    with pytest.raises(ValueError):
        f.save({"forward": "nope"}, version)
    assert json.loads(path.read_text()) == {"forward": {"chats": ["A"]}}
