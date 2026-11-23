import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from . import destinations
from .rules import decide
from .settings import Conflict, Settings

log = logging.getLogger(__name__)


class Unsupported(Exception):
    pass


class Api:
    def __init__(self, settings_file, chatlog):
        self.settings_file = settings_file
        self.chatlog = chatlog

    def state(self):
        s, version = self.settings_file.get()
        return {
            "version": version,
            "forward": s.raw["forward"],
            "ignore": s.raw["ignore"],
            "destinations": [{"id": i, **destinations.describe(u)} for i, u in enumerate(s.raw["destinations"])],
            "chats": self.chatlog.list(),
        }

    def _url(self, ref, current):
        """A destination is sent back as {"id": n} for a saved one, so its secret never reaches the page."""
        if "id" in ref:
            return current.raw["destinations"][int(ref["id"])]
        url = str(ref.get("url", ""))
        if not destinations.is_valid(url):
            raise ValueError("a new destination is not a valid Apprise URL")
        return url

    def save(self, req):
        current, version = self.settings_file.get()
        # Saved destinations come back as indexes into the settings the page
        # loaded, so they mean nothing once the file has changed under it.
        if str(req.get("version")) != version:
            raise Conflict()
        urls = [self._url(d, current) for d in req.get("destinations", [])]
        raw = {"destinations": urls, "forward": req.get("forward"), "ignore": req.get("ignore")}
        self.settings_file.save(raw, str(req.get("version")))
        log.info("settings: saved from the settings page")
        return self.state()

    def test(self, req):
        current, _ = self.settings_file.get()
        return {"ok": destinations.send_test(self._url(req, current))}

    def check(self, req):
        rules = Settings({"forward": req.get("forward"), "ignore": req.get("ignore")})
        send, reason = decide(rules, str(req.get("chat", "")), str(req.get("text", "")))
        return {"send": send, "reason": reason}


def make_handler(api):
    page = resources.files(__package__).joinpath("static/index.html").read_bytes()
    writes = {
        ("PUT", "/api/settings"): api.save,
        ("POST", "/api/test"): api.test,
        ("POST", "/api/check"): api.check,
    }

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

        def body(self):
            # Plain form posts from other sites cannot set this content type,
            # so requiring it keeps the login cookie from being used against us.
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise Unsupported("expected application/json")
            return json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self.reply(200, page, "text/html")
            elif self.path == "/api/state":
                self.reply(200, api.state())
            else:
                self.reply(404, {"error": "not found"})

        def write(self):
            action = writes.get((self.command, self.path))
            if not action:
                return self.reply(404, {"error": "not found"})
            try:
                self.reply(200, action(self.body()))
            except Unsupported as e:
                self.reply(415, {"error": str(e)})
            except Conflict as e:
                self.reply(409, {"error": str(e)})
            except (ValueError, KeyError, IndexError, TypeError) as e:
                self.reply(400, {"error": str(e)})

        do_PUT = write
        do_POST = write

    return Handler


def make_server(api, host, port):
    return ThreadingHTTPServer((host, port), make_handler(api))
