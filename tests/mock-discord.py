import http.server
import json
import ssl


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with open("/tmp/discord-posts.jsonl", "a") as f:
            f.write(json.dumps({"path": self.path, "body": body}, ensure_ascii=False) + "\n")
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


server = http.server.HTTPServer(("127.0.0.1", 443), Handler)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain("/config/certs/web-fullchain.pem", "/config/certs/web-privkey.pem")
server.socket = ctx.wrap_socket(server.socket, server_side=True)
server.serve_forever()
