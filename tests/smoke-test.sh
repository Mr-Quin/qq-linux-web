#!/usr/bin/env bash
# Usage: smoke-test.sh IMAGE
# Starts IMAGE with an empty config, checks that QQ and the web UI come up, and
# that the notification forwarder posts the right notifications to a fake
# Discord. Never point this at the real config: QQ allows one login at a time.
set -euo pipefail

image=$1
here=$(cd "$(dirname "$0")" && pwd)
name=qq-smoke-$$
config=$(mktemp -d)

cleanup() {
    docker rm -f "$name" >/dev/null 2>&1 || true
    # The container's files belong to its own user, so delete them from inside one.
    docker run --rm -v "$config:/c" --entrypoint find "$image" /c -mindepth 1 -delete >/dev/null 2>&1 || true
    rmdir "$config" 2>/dev/null || true
}
trap cleanup EXIT

fail() {
    echo "FAIL: $*"
    docker logs --tail 40 "$name" 2>&1 | sed 's/^/  | /'
    exit 1
}

wait_for() {
    local what=$1 tries=$2
    shift 2
    for _ in $(seq "$tries"); do
        "$@" >/dev/null 2>&1 && return 0
        sleep 2
    done
    fail "$what"
}

in_app() {
    docker exec -u 1000 -e DBUS_SESSION_BUS_ADDRESS=unix:path=/tmp/dbus.base "$name" "$@"
}

write_settings() {
    docker exec -u 1000 "$name" sh -c \
        'printf "%s\n" "$1" > /config/notify-forward.json.new && mv /config/notify-forward.json.new /config/notify-forward.json' \
        sh "$1"
}

notify() {
    in_app python3 -c '
import json, sys, dbus
n = dbus.Interface(
    dbus.SessionBus().get_object("org.freedesktop.Notifications", "/org/freedesktop/Notifications"),
    "org.freedesktop.Notifications",
)
for app, title, body in json.loads(sys.argv[1]):
    n.Notify(app, 0, "", title, body, [], {}, 5000)
' "$1" >/dev/null
    sleep 5
}

posts() {
    docker exec "$name" cat /tmp/discord-posts.jsonl 2>/dev/null || true
}

web() {
    docker exec "$name" curl -sk -b /tmp/smoke-cookies -c /tmp/smoke-cookies "$@"
}

api() {
    local method=$1 path=$2
    shift 2
    web -X "$method" -H "Content-Type: application/json" "https://127.0.0.1:5800/notify/api/$path" "$@"
}

json() {
    docker exec "$name" python3 -c 'import json, sys; print(eval(sys.argv[2], {"d": json.loads(sys.argv[1])}))' "$1" "$2"
}

docker run -d --name "$name" \
    -e USER_ID=1000 -e GROUP_ID=1000 \
    -e WEB_AUTHENTICATION=1 -e WEB_AUTHENTICATION_USERNAME=smoke -e WEB_AUTHENTICATION_PASSWORD=smoke-test-only \
    --add-host discord.com:127.0.0.1 \
    -v "$config:/config" -v "$here/mock_webhook.py:/smoke/mock_webhook.py:ro" \
    --shm-size 1g --security-opt seccomp=unconfined \
    "$image" >/dev/null

wait_for "web UI did not answer" 60 docker exec "$name" curl -fsk -o /dev/null https://127.0.0.1:5800/
wait_for "QQ did not start" 60 docker exec "$name" pgrep -x qq
wait_for "QQ did not create its profile" 60 docker exec "$name" test -d /config/xdg/config/QQ
sleep 15
docker exec "$name" pgrep -x qq >/dev/null || fail "QQ exited after starting"
if docker logs "$name" 2>&1 | grep -q "service 'app' exited"; then
    fail "QQ crashed and was restarted"
fi
echo "ok: QQ and the web UI are up"

qq_visible() {
    [ -n "$(docker exec -u 1000 -e DISPLAY=:0 "$name" xdotool search --onlyvisible --class QQ 2>/dev/null)" ]
}
qq_hidden() {
    ! qq_visible
}
wait_for "QQ was not hidden while nobody was watching" 20 qq_hidden
docker exec -u 1000 -d "$name" python3 -c '
import socket, time
s = socket.socket(socket.AF_UNIX); s.connect("/tmp/vnc.sock"); time.sleep(20)'
wait_for "QQ did not come back when a viewer connected" 8 qq_visible
wait_for "QQ was not hidden again after the viewer left" 30 qq_hidden
echo "ok: QQ hides while nobody watches, so it sends notifications, and comes back for a viewer"

docker exec -u 0 -d "$name" python3 /smoke/mock_webhook.py --port 443 \
    --log /tmp/discord-posts.jsonl --tls /config/certs/web-fullchain.pem /config/certs/web-privkey.pem
wait_for "mock Discord did not start" 15 docker exec "$name" curl -fsk -o /dev/null -X POST -H "Content-Length: 2" -d '{}' https://127.0.0.1/ping
docker exec -u 0 "$name" rm -f /tmp/discord-posts.jsonl

wait_for "forwarder did not create its settings file" 15 docker exec "$name" test -f /config/notify-forward.json
write_settings '{
  "destinations": ["discord://1234/smoketoken?verify=no"],
  "forward": {"chats": ["Smoke Chat"], "keywords": ["@我"]},
  "ignore": {"chats": ["Noisy Group"], "keywords": ["广告"]}
}'
notify '[
  ["QQ", "Smoke Chat", "listed chat"],
  ["QQ", "Other Chat", "not listed"],
  ["QQ", "Some Group", "Bob: [有人@我] mention"],
  ["QQ", "Noisy Group", "Amy: [有人@我] noisy mention"],
  ["QQ", "Noisy Group", "chatter"],
  ["QQ", "Smoke Chat", "广告 spam"],
  ["Firefox", "Smoke Chat", "not QQ"]
]'

p=$(posts)
count=$(grep -c . <<<"$p" || true)
[ "$count" = 3 ] || fail "expected 3 Discord posts, got $count: $p"
grep -q '"/api/webhooks/1234/smoketoken' <<<"$p" || fail "posted to the wrong webhook path: $p"
grep -q "listed chat" <<<"$p" || fail "listed chat was not forwarded: $p"
grep -q "Bob: \[有人@我\] mention" <<<"$p" || fail "mention was not forwarded: $p"
grep -q "noisy mention" <<<"$p" || fail "mention in an ignored chat was not forwarded: $p"
if grep -q -e "广告" -e "chatter" <<<"$p"; then
    fail "ignored chat or keyword was forwarded: $p"
fi
docker logs "$name" 2>&1 | grep -q "dropped: chat 'Noisy Group', ignored chat" || fail "forwarder did not log its decisions"
echo "ok: forwarder applied the forward and ignore rules"

write_settings '{
  "destinations": ["discord://1234/smoketoken?verify=no"],
  "forward": {"chats": ["*"], "keywords": []},
  "ignore": {"chats": [], "keywords": []}
}'
notify '[["QQ", "Other Chat", "after reload"]]'
grep -q "after reload" <<<"$(posts)" || fail "changed settings were not picked up"

write_settings '{ not json'
notify '[["QQ", "Other Chat", "after broken file"]]'
grep -q "after broken file" <<<"$(posts)" || fail "a broken settings file dropped the previous settings"
docker logs "$name" 2>&1 | grep -q "is invalid, keeping the previous settings" || fail "broken settings file was not reported"
echo "ok: settings reload without a restart, and a broken file keeps the last good ones"
unauth=$(web -o /dev/null -w '%{http_code} %{redirect_url}' https://127.0.0.1:5800/notify/api/state)
[[ $unauth == "302 "*/login/ ]] || fail "settings page answered without a login: $unauth"
web -o /dev/null https://127.0.0.1:5800/notify/
web -o /dev/null -d username=smoke -d password=smoke-test-only https://127.0.0.1:5800/login/login
web https://127.0.0.1:5800/notify/ | grep -q "QQ notification forwarding" || fail "settings page did not load after login"

state=$(api GET state)
[ "$(json "$state" 'len(d["destinations"])')" = 1 ] || fail "settings page does not list the destination: $state"
if grep -q smoketoken <<<"$state"; then
    fail "settings page shows a destination's secret: $state"
fi
[ "$(json "$state" '"Noisy Group" in [c["chat"] for c in d["chats"]]')" = True ] || fail "recent chats are missing: $state"
if grep -q -e "chatter" -e "noisy mention" <<<"$state"; then
    fail "recent chats include message text: $state"
fi
echo "ok: settings page needs the login, hides secrets and lists recent chats"

version=$(json "$state" 'd["version"]')
saved=$(api PUT settings -d '{"version": "'"$version"'", "destinations": [{"id": 0}],
    "forward": {"chats": ["Smoke Chat"], "keywords": []}, "ignore": {"chats": ["Other Chat"], "keywords": []}}')
[ "$(json "$saved" 'd["ignore"]["chats"]')" = "['Other Chat']" ] || fail "saving from the page failed: $saved"
docker exec "$name" grep -q smoketoken /config/notify-forward.json || fail "saving from the page lost the destination URL"
notify '[["QQ", "Other Chat", "after page save"], ["QQ", "Smoke Chat", "listed after page save"]]'
grep -q "after page save" <<<"$(posts | grep -v listed)" && fail "a chat ignored from the page was still forwarded"
grep -q "listed after page save" <<<"$(posts)" || fail "a chat forwarded from the page was not forwarded"

stale=$(api PUT settings -o /dev/null -w '%{http_code}' -d '{"version": "'"$version"'", "destinations": []}')
[ "$stale" = 409 ] || fail "saving over newer settings was not refused: $stale"
form=$(web -o /dev/null -w '%{http_code}' -X PUT -d 'x=1' https://127.0.0.1:5800/notify/api/settings)
[ "$form" = 415 ] || fail "a form post to the settings API was not refused: $form"
check=$(api POST check -d '{"chat": "Noisy Group", "text": "[有人@我]",
    "forward": {"chats": [], "keywords": ["@我"]}, "ignore": {"chats": ["Noisy Group"], "keywords": []}}')
[ "$(json "$check" 'd["reason"]')" = "keyword '@我'" ] || fail "rule tester gave the wrong answer: $check"
api POST test -d '{"id": 0}' >/dev/null
sleep 2
grep -q "Test message from the QQ settings page" <<<"$(posts)" || fail "test button did not reach the destination"
echo "ok: saving, conflicts, form posts, the rule tester and the test button work"
echo "PASS: $image"
