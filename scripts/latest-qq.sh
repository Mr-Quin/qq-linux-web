#!/usr/bin/env bash
# Prints the x86_64 .deb URL and its SHA-512 for the newest Linux QQ, taken from
# the AUR linuxqq package. Tencent's own release links refuse plain downloads.
set -euo pipefail

srcinfo=$(curl -fsSL "https://aur.archlinux.org/cgit/aur.git/plain/.SRCINFO?h=linuxqq")
url=$(awk -F' = ' '$1 ~ /^\tsource_x86_64$/ {print $2}' <<<"$srcinfo")
sha=$(awk -F' = ' '$1 ~ /^\tsha512sums_x86_64$/ {print $2}' <<<"$srcinfo")
[[ $url == https://qqdl.gtimg.cn/* && $sha =~ ^[0-9a-f]{128}$ ]]
echo "$url $sha"
