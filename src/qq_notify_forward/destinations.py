import apprise


def defang(text):
    # A message quoting @everyone must not ping the whole Discord server.
    return text.replace("@everyone", "@​everyone").replace("@here", "@​here")


def is_valid(url):
    return bool(apprise.Apprise.instantiate(url))


def describe(url):
    plugin = apprise.Apprise.instantiate(url)
    if not plugin:
        return {"service": "invalid", "display": "not a valid Apprise URL"}
    return {"service": plugin.service_name, "display": plugin.url(privacy=True).split("?")[0]}


def send_test(url):
    target = apprise.Apprise()
    if not target.add(url):
        raise ValueError("not a valid Apprise URL")
    return bool(target.notify(title="QQ forwarder", body="Test message from the QQ settings page."))


def send(notifier, chat, body):
    return bool(notifier.notify(title=defang(chat), body=defang(body) or " ", body_format=apprise.NotifyFormat.TEXT))
