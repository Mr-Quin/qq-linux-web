import logging

from . import destinations
from .rules import decide

log = logging.getLogger(__name__)


class Forwarder:
    def __init__(self, settings_file, chatlog):
        self.settings_file = settings_file
        self.chatlog = chatlog

    def handle(self, app_name, chat, body):
        """Applies the rules to one desktop notification. Returns the verdict, or None if it isn't QQ's."""
        if "qq" not in app_name.lower():
            return None
        settings, _ = self.settings_file.get()
        send, reason = decide(settings, chat, body)
        if send and not len(settings.notifier):
            send, reason = False, f"{reason}, but no destinations are set"
        if send:
            verdict = "sent" if destinations.send(settings.notifier, chat, body) else "send failed"
        else:
            verdict = "dropped"
        self.chatlog.record(chat, verdict, reason)
        log.info("%s: chat %r, %s", verdict, chat, reason)
        return verdict
