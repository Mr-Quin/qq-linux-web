import json
import logging
import threading
import time

from .settings import write_private

log = logging.getLogger(__name__)

MAX_CHATS = 300


class ChatLog:
    """Chat names QQ has notified about, with the last decision. Never message text."""

    def __init__(self, path, clock=time.time):
        self.path = path
        self.clock = clock
        self.lock = threading.Lock()
        try:
            with open(path) as f:
                self.chats = json.load(f)
        except (OSError, ValueError):
            self.chats = {}

    def record(self, chat, verdict, reason):
        with self.lock:
            entry = self.chats.setdefault(chat, {"count": 0})
            entry.update(last=int(self.clock()), verdict=verdict, reason=reason, count=entry["count"] + 1)
            if len(self.chats) > MAX_CHATS:
                oldest = sorted(self.chats, key=lambda c: self.chats[c]["last"])
                for c in oldest[: len(self.chats) - MAX_CHATS]:
                    del self.chats[c]
            try:
                write_private(self.path, self.chats)
            except OSError as e:
                log.warning("chats: cannot save %s: %s", self.path, e)

    def list(self):
        with self.lock:
            return sorted(({"chat": c, **e} for c, e in self.chats.items()), key=lambda e: e["last"], reverse=True)
