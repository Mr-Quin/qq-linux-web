import argparse
import logging
import os
import threading

from .api import Api, make_server
from .chatlog import ChatLog
from .forwarder import Forwarder
from .settings import SettingsFile


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="qq-notify-forward", description="Forward QQ desktop notifications.")
    p.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "serve"],
        help="run: settings page and forwarding (default). serve: settings page only.",
    )
    p.add_argument("--settings", default=os.environ.get("QQ_NOTIFY_SETTINGS", "/config/notify-forward.json"))
    p.add_argument("--chats", default=os.environ.get("QQ_NOTIFY_CHATS", "/config/notify-forward-chats.json"))
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8081)
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings_file = SettingsFile(args.settings)
    settings_file.get()
    chatlog = ChatLog(args.chats)
    server = make_server(Api(settings_file, chatlog), args.host, args.port)

    if args.command == "serve":
        server.serve_forever()
        return

    from .monitor import watch_notifications

    forwarder = Forwarder(settings_file, chatlog)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    watch_notifications(forwarder.handle)


if __name__ == "__main__":
    main()
