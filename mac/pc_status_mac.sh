#!/bin/bash
# 轮询 macOS 前台应用并上报到 sleepy（pc_status / pc_app_name）。
# 用法: bash mac/pc_status_mac.sh
# 依赖: swiftc（Xcode Command Line Tools）、curl、plutil
set -u

BASE="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$BASE/data.json"
FRONTAPP="$BASE/mac/frontapp"
SERVER="${SLEEPY_SERVER:-http://127.0.0.1:9010}"

if [ ! -f "$DATA" ]; then
    echo "data.json not found: $DATA (先运行一次 python3 server.py 生成)" >&2
    exit 1
fi

if [ ! -x "$FRONTAPP" ]; then
    echo "building mac/frontapp ..." >&2
    xcrun swiftc -O "$BASE/mac/frontapp.swift" -o "$FRONTAPP" || exit 1
fi

SECRET=$(/usr/bin/plutil -extract secret raw -o - "$DATA" 2>/dev/null)
if [ -z "$SECRET" ]; then
    echo "cannot read secret from $DATA" >&2
    exit 1
fi

LAST=""
while true; do
    APP=$("$FRONTAPP" 2>/dev/null)
    if [ -n "$APP" ] && [ "$APP" != "$LAST" ]; then
        /usr/bin/curl -sG --max-time 5 "$SERVER/set" \
            --data-urlencode "secret=$SECRET" \
            --data-urlencode "pc_status=0" \
            --data-urlencode "pc_app_name=$APP" >/dev/null 2>&1
        LAST="$APP"
    fi
    sleep 2
done
