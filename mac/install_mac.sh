#!/bin/bash
# 在 macOS 上安装 sleepy 服务端 + 前台应用上报的 launchd 服务。
# 用法: bash mac/install_mac.sh
# 说明: 需要在仓库根目录有 data.json（先运行一次 python3 server.py 生成），并已安装 Xcode Command Line Tools。
set -euo pipefail

BASE="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
AGENTS="$HOME/Library/LaunchAgents"
LOGS="$HOME/Library/Logs"
UID_NUM="$(id -u)"

mkdir -p "$AGENTS" "$LOGS"

echo "==> 安装 Python 依赖"
if [ ! -d "$BASE/venv" ]; then
    "$PYTHON" -m venv "$BASE/venv"
fi
"$BASE/venv/bin/pip" install -q -r "$BASE/requirements.txt" waitress

echo "==> 编译前台应用检测器"
xcrun swiftc -O "$BASE/mac/frontapp.swift" -o "$BASE/mac/frontapp"

echo "==> 写入 LaunchAgents"
cat > "$AGENTS/com.sleepy.server.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.sleepy.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>$BASE/venv/bin/waitress-serve</string>
        <string>--host=127.0.0.1</string>
        <string>--port=9010</string>
        <string>--threads=4</string>
        <string>server:app</string>
    </array>
    <key>WorkingDirectory</key><string>$BASE</string>
    <key>EnvironmentVariables</key>
    <dict><key>PYTHONDONTWRITEBYTECODE</key><string>1</string></dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$LOGS/sleepy-server.log</string>
    <key>StandardErrorPath</key><string>$LOGS/sleepy-server.log</string>
</dict>
</plist>
PLIST

cat > "$AGENTS/com.sleepy.pcstatus.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.sleepy.pcstatus</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$BASE/mac/pc_status_mac.sh</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$LOGS/sleepy-pcstatus.log</string>
    <key>StandardErrorPath</key><string>$LOGS/sleepy-pcstatus.log</string>
</dict>
</plist>
PLIST

echo "==> 加载服务"
for label in com.sleepy.server com.sleepy.pcstatus; do
    launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
    launchctl bootstrap "gui/$UID_NUM" "$AGENTS/$label.plist"
done

echo "完成。"
echo "  服务端: http://127.0.0.1:9010/"
echo "  日志:   ~/Library/Logs/sleepy-server.log"
echo "          ~/Library/Logs/sleepy-pcstatus.log"
