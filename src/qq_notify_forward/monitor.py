import logging
import time

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

log = logging.getLogger(__name__)

NOTIFICATIONS = "org.freedesktop.Notifications"


def watch_notifications(on_notify):
    """Calls on_notify(app_name, summary, body) for every Notify call on the session bus. Never returns."""

    def on_message(_bus, msg):
        if msg.get_member() != "Notify":
            return
        args = msg.get_args_list()
        if len(args) >= 5:
            on_notify(str(args[0]), str(args[3]), str(args[4]))

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    # libnotify gives up when nothing owns the name, so QQ's notifications would
    # never reach the bus at all.
    for _ in range(30):
        if bus.name_has_owner(NOTIFICATIONS):
            break
        time.sleep(1)
    else:
        log.warning("warning: nothing accepts desktop notifications, so QQ's never arrive; set WEB_NOTIFICATION=1")
    bus.add_message_filter(on_message)
    bus.call_blocking(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus.Monitoring",
        "BecomeMonitor",
        "asu",
        ([f"type='method_call',interface='{NOTIFICATIONS}',member='Notify'"], 0),
    )
    GLib.MainLoop().run()
