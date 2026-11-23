#!/usr/bin/python3
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import apprise
import dbus
import dbus.mainloop.glib
from gi.repository import GLib

SETTINGS_PATH = os.environ.get("QQ_NOTIFY_SETTINGS", "/config/notify-forward.json")
CHATS_PATH = os.environ.get("QQ_NOTIFY_CHATS", "/config/notify-forward-chats.json")
PAGE_PATH = "/usr/local/share/notify-forward/index.html"
LISTEN = ("127.0.0.1", 8081)
MAX_CHATS = 300

DEFAULT_SETTINGS = {
    "destinations": [],
    "forward": {"chats": [], "keywords": ["@我"]},
    "ignore": {"chats": [], "keywords": []},
}


def log(message):
    print(message, flush=True)


def write_private(path, data):
    tmp = f"{path}.new"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def normalize(raw):
    def strings(value, what):
        if value is None:
            return []
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError(f"{what} must be a list of strings")
        return list(dict.fromkeys(v.strip() for v in value if v.strip()))

    def section(name):
        value = raw.get(name) or {}
        if not isinstance(value, dict):
            raise ValueError(f"{name} must be an object")
        return {
            "chats": strings(value.get("chats"), f"{name}.chats"),
            "keywords": strings(value.get("keywords"), f"{name}.keywords"),
        }

    if not isinstance(raw, dict):
        raise ValueError("settings must be an object")
    return {
        "destinations": strings(raw.get("destinations"), "destinations"),
        "forward": section("forward"),
        "ignore": section("ignore"),
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
                log(f"settings: destination {i} is not a valid Apprise URL")

    def summary(self):
        return (
            f"{len(self.notifier)} destinations, "
            f"{len(self.forward_chats)} chats and {len(self.forward_keywords)} keywords forwarded, "
            f"{len(self.ignore_chats)} chats and {len(self.ignore_keywords)} keywords ignored"
        )


class Conflict(Exception):
    pass


class SettingsFile:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.mtime = None
        self.current = Settings(DEFAULT_SETTINGS)
        if not os.path.exists(path):
            write_private(path, DEFAULT_SETTINGS)
            log(f"settings: created {path} with no destinations")

    def get(self):
        with self.lock:
            try:
                mtime = os.stat(self.path).st_mtime_ns
            except OSError as e:
                log(f"settings: cannot read {self.path}, keeping the previous settings: {e}")
                return self.current, str(self.mtime)
            if mtime != self.mtime:
                self.mtime = mtime
                try:
                    with open(self.path) as f:
                        self.current = Settings(json.load(f))
                    log(f"settings: loaded {self.current.summary()}")
                except (OSError, ValueError) as e:
                    log(f"settings: {self.path} is invalid, keeping the previous settings: {e}")
            return self.current, str(self.mtime)

    def save(self, raw, version):
        settings = Settings(raw)
        with self.lock:
            if version != str(self.mtime):
                raise Conflict("the settings changed since this page loaded them; reload and try again")
            write_private(self.path, settings.raw)
        return self.get()


class ChatLog:
    """Chat names QQ has notified about, with the last decision. Never message text."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        try:
            with open(path) as f:
                self.chats = json.load(f)
        except (OSError, ValueError):
            self.chats = {}

    def record(self, chat, verdict, reason):
        with self.lock:
            entry = self.chats.setdefault(chat, {"count": 0})
            entry.update(last=int(time.time()), verdict=verdict, reason=reason, count=entry["count"] + 1)
            if len(self.chats) > MAX_CHATS:
                oldest = sorted(self.chats, key=lambda c: self.chats[c]["last"])
                for c in oldest[: len(self.chats) - MAX_CHATS]:
                    del self.chats[c]
            try:
                write_private(self.path, self.chats)
            except OSError as e:
                log(f"chats: cannot save {self.path}: {e}")

    def list(self):
        with self.lock:
            return sorted(
                ({"chat": c, **e} for c, e in self.chats.items()), key=lambda e: e["last"], reverse=True
            )


def first_match(keywords, text):
    return next((k for k in keywords if k in text), None)


def decide(s, chat, body):
    text = f"{chat}\n{body}"
    if k := first_match(s.ignore_keywords, text):
        return False, f"ignored keyword {k!r}"
    if k := first_match(s.forward_keywords, text):
        return True, f"keyword {k!r}"
    if chat in s.ignore_chats:
        return False, "ignored chat"
    if chat in s.forward_chats:
        return True, "listed chat"
    if "*" in s.forward_chats:
        return True, "all chats"
    return False, "no rule matched"


def defang(text):
    # A message quoting @everyone must not ping the whole Discord server.
    return text.replace("@everyone", "@​everyone").replace("@here", "@​here")


def describe(url):
    plugin = apprise.Apprise.instantiate(url)
    if not plugin:
        return {"service": "invalid", "display": "not a valid Apprise URL"}
    return {"service": plugin.service_name, "display": plugin.url(privacy=True).split("?")[0]}


def make_handler(settings, chats):
    with open(PAGE_PATH, "rb") as f:
        page = f.read()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body, content_type="application/json"):
            if content_type == "application/json":
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def state(self):
            s, version = settings.get()
            return {
                "version": version,
                "forward": s.raw["forward"],
                "ignore": s.raw["ignore"],
                "destinations": [{"id": i, **describe(u)} for i, u in enumerate(s.raw["destinations"])],
                "chats": chats.list(),
            }

        def body(self):
            # Plain form posts from other sites cannot set this content type,
            # so requiring it keeps the login cookie from being used against us.
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise PermissionError("expected application/json")
            return json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self.reply(200, page, "text/html")
            elif self.path == "/api/state":
                self.reply(200, self.state())
            else:
                self.reply(404, {"error": "not found"})

        def handle_write(self, action):
            try:
                self.reply(200, action(self.body()))
            except PermissionError as e:
                self.reply(415, {"error": str(e)})
            except Conflict as e:
                self.reply(409, {"error": str(e)})
            except (ValueError, KeyError, IndexError, TypeError) as e:
                self.reply(400, {"error": str(e)})

        def do_PUT(self):
            if self.path != "/api/settings":
                return self.reply(404, {"error": "not found"})

            def save(req):
                current, _ = settings.get()
                urls = []
                for d in req.get("destinations", []):
                    if "id" in d:
                        urls.append(current.raw["destinations"][int(d["id"])])
                    elif apprise.Apprise.instantiate(str(d.get("url", ""))):
                        urls.append(str(d["url"]))
                    else:
                        raise ValueError("a new destination is not a valid Apprise URL")
                raw = {"destinations": urls, "forward": req.get("forward"), "ignore": req.get("ignore")}
                settings.save(raw, str(req.get("version")))
                log("settings: saved from the settings page")
                return self.state()

            self.handle_write(save)

        def do_POST(self):
            def test(req):
                if "id" in req:
                    url = settings.get()[0].raw["destinations"][int(req["id"])]
                else:
                    url = str(req.get("url", ""))
                target = apprise.Apprise()
                if not target.add(url):
                    raise ValueError("not a valid Apprise URL")
                ok = target.notify(title="QQ forwarder", body="Test message from the QQ settings page.")
                return {"ok": bool(ok)}

            def check(req):
                rules = Settings({"forward": req.get("forward"), "ignore": req.get("ignore")})
                send, reason = decide(rules, str(req.get("chat", "")), str(req.get("text", "")))
                return {"send": send, "reason": reason}

            actions = {"/api/test": test, "/api/check": check}
            if self.path not in actions:
                return self.reply(404, {"error": "not found"})
            self.handle_write(actions[self.path])

    return Handler


def main():
    settings = SettingsFile(SETTINGS_PATH)
    settings.get()
    chats = ChatLog(CHATS_PATH)

    server = ThreadingHTTPServer(LISTEN, make_handler(settings, chats))
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def on_message(_bus, msg):
        if msg.get_member() != "Notify":
            return
        args = msg.get_args_list()
        if len(args) < 5:
            return
        app_name, chat, body = str(args[0]), str(args[3]), str(args[4])
        if "qq" not in app_name.lower():
            return
        s, _ = settings.get()
        send, reason = decide(s, chat, body)
        if send and not len(s.notifier):
            send, reason = False, f"{reason}, but no destinations are set"
        sent = send and s.notifier.notify(
            title=defang(chat), body=defang(body) or " ", body_format=apprise.NotifyFormat.TEXT
        )
        verdict = ("sent" if sent else "send failed") if send else "dropped"
        chats.record(chat, verdict, reason)
        log(f"{verdict}: chat {chat!r}, {reason}")

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    for _ in range(30):
        if bus.name_has_owner("org.freedesktop.Notifications"):
            break
        time.sleep(1)
    else:
        log("warning: nothing accepts desktop notifications, so QQ's never arrive; set WEB_NOTIFICATION=1")
    bus.add_message_filter(on_message)
    bus.call_blocking(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus.Monitoring",
        "BecomeMonitor",
        "asu",
        (["type='method_call',interface='org.freedesktop.Notifications',member='Notify'"], 0),
    )
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
