#!/usr/bin/env bash
# Usage: fetch-qq.sh DIR
# Downloads the QQ .deb pinned in the Dockerfile to DIR/linuxqq.deb and checks
# its SHA-512. Pass DIR to docker build as --build-context qq-deb=DIR so the
# build doesn't depend on reaching Tencent's CDN itself.
set -euo pipefail

dir=$1
root=$(cd "$(dirname "$0")/.." && pwd)
url=$(sed -n 's/^ARG QQ_URL=//p' "$root/Dockerfile")
sha=$(sed -n 's/^ARG QQ_SHA512=//p' "$root/Dockerfile")
deb=$dir/linuxqq.deb

mkdir -p "$dir"
if [ -f "$deb" ] && echo "$sha  $deb" | sha512sum -c --status -; then
    echo "already have $(basename "$url")"
    exit 0
fi

# The CDN sometimes refuses connections for minutes at a time.
for attempt in 1 2 3 4 5 6; do
    if curl -fL --retry 3 --retry-all-errors --connect-timeout 20 --max-time 600 -o "$deb.part" "$url"; then
        break
    fi
    [ "$attempt" = 6 ] && exit 1
    sleep $((attempt * 30))
done
echo "$sha  $deb.part" | sha512sum -c -
mv "$deb.part" "$deb"
