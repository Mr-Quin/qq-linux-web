def _first_match(keywords, text):
    return next((k for k in keywords if k in text), None)


def decide(settings, chat, body):
    """Returns (send, reason). The first matching rule wins."""
    text = f"{chat}\n{body}"
    if k := _first_match(settings.ignore_keywords, text):
        return False, f"ignored keyword {k!r}"
    if k := _first_match(settings.forward_keywords, text):
        return True, f"keyword {k!r}"
    if chat in settings.ignore_chats:
        return False, "ignored chat"
    if chat in settings.forward_chats:
        return True, "listed chat"
    if "*" in settings.forward_chats:
        return True, "all chats"
    return False, "no rule matched"
