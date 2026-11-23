"""A stand-in for webhook services, used by every test layer.

Records each POST it receives. GET /posts lists them and DELETE /posts clears
them. With --tls it answers HTTPS, so the smoke test can point discord.com at
it and exercise Apprise's real Discord plugin.
"""

import argparse
import json
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class MockWebhook:
    def __init__(self, host="127.0.0.1", port=0, log_path=None):
        self.posts = []
        self.lock = threading.Lock()
        self.log_path = log_path
        self.server = ThreadingHTTPServer((host, port), self._handler())

    @property
    def url(self):
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    def start(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def clear(self):
        with self.lock:
            self.posts.clear()

    def _record(self, post):
        with self.lock:
            self.posts.append(post)
            if self.log_path:
                with open(self.log_path, "a") as f:
                    f.write(json.dumps(post, ensure_ascii=False) + "\n")

    def _handler(self):
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, body=None):
                data = json.dumps(body, ensure_ascii=False).encode() if body is not None else b""
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                try:
                    body = json.loads(raw or b"null")
                except ValueError:
                    body = raw.decode(errors="replace")
                mock._record({"path": self.path, "body": body})
                self.reply(204)

            def do_GET(self):
                if self.path != "/posts":
                    return self.reply(404, {"error": "not found"})
                with mock.lock:
                    self.reply(200, list(mock.posts))

            def do_DELETE(self):
                mock.clear()
                self.reply(204)

        return Handler


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8090)
    p.add_argument("--log", help="also append each post to this file as a JSON line")
    p.add_argument("--tls", nargs=2, metavar=("CERT", "KEY"))
    args = p.parse_args()

    mock = MockWebhook(args.host, args.port, args.log)
    if args.tls:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(*args.tls)
        mock.server.socket = ctx.wrap_socket(mock.server.socket, server_side=True)
    print(f"mock webhook on {args.host}:{args.port}", flush=True)
    mock.server.serve_forever()


if __name__ == "__main__":
    main()
