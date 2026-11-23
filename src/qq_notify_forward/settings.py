import json
import logging
import os
import threading

import apprise

log = logging.getLogger(__name__)

DEFAULT_SETTINGS = {
    "destinations": [],
    "forward": {"chats": [], "keywords": ["@我"]},
    "ignore": {"chats": [], "keywords": []},
}


def write_private(path, data):
    tmp = f"{path}.new"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _strings(value, what):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{what} must be a list of strings")
    return list(dict.fromkeys(v.strip() for v in value if v.strip()))


def _section(raw, name):
    value = raw.get(name)
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return {
        "chats": _strings(value.get("chats"), f"{name}.chats"),
        "keywords": _strings(value.get("keywords"), f"{name}.keywords"),
    }


def normalize(raw):
    if not isinstance(raw, dict):
        raise ValueError("settings must be an object")
    return {
        "destinations": _strings(raw.get("destinations"), "destinations"),
        "forward": _section(raw, "forward"),
        "ignore": _section(raw, "ignore"),
    }


class Settings:
    def __init__(self, raw):
        self.raw = normalize(raw)
        self.forward_chats = set(self.raw["forward"]["chats"])
        self.forward_keywords = self.raw["forward"]["keywords"]
        self.ignore_chats = set(self.raw["ignore"]["chats"])
        self.ignore_keywords = self.raw["ignore"]["keywords"]
        self.notifier = apprise.Apprise()
        for i, url in enumerate(self.raw["destinations"], 1):
            if not self.notifier.add(url):
                log.warning("settings: destination %d is not a valid Apprise URL", i)

    def summary(self):
        return (
            f"{len(self.notifier)} destinations, "
            f"{len(self.forward_chats)} chats and {len(self.forward_keywords)} keywords forwarded, "
            f"{len(self.ignore_chats)} chats and {len(self.ignore_keywords)} keywords ignored"
        )


class Conflict(Exception):
    def __init__(self):
        super().__init__("the settings changed since this page loaded them; reload and try again")


class SettingsFile:
    """The settings file, reloaded whenever its mtime changes.

    The mtime doubles as the version the settings page sends back on save, so
    that a save over an edit made elsewhere is refused instead of lost.
    """

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.mtime = None
        self.current = Settings(DEFAULT_SETTINGS)
        if not os.path.exists(path):
            write_private(path, DEFAULT_SETTINGS)
            log.info("settings: created %s with no destinations", path)

    def get(self):
        with self.lock:
            try:
                mtime = os.stat(self.path).st_mtime_ns
            except OSError as e:
                log.warning("settings: cannot read %s, keeping the previous settings: %s", self.path, e)
                return self.current, str(self.mtime)
            if mtime != self.mtime:
                self.mtime = mtime
                try:
                    with open(self.path) as f:
                        self.current = Settings(json.load(f))
                    log.info("settings: loaded %s", self.current.summary())
                except (OSError, ValueError) as e:
                    log.warning("settings: %s is invalid, keeping the previous settings: %s", self.path, e)
            return self.current, str(self.mtime)

    def save(self, raw, version):
        settings = Settings(raw)
        with self.lock:
            if version != str(self.mtime):
                raise Conflict()
            write_private(self.path, settings.raw)
        return self.get()
