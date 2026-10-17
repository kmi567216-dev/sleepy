# sleepy on Linux

把 sleepy 从 macOS 迁到 Linux 服务器（VPS / 家宽小主机）时，大部分东西不用改：Flask 代码、`data.json`、secret、手机 MacroDroid、Cloudflare Tunnel、页面和接口都一样。需要替换的只有进程管理和 Mac 前台检测。

## 和 macOS 的差异

| 项目 | macOS | Linux |
| --- | --- | --- |
| 常驻 | launchd (`~/Library/LaunchAgents`) | systemd (`/etc/systemd/system`) |
| WSGI | waitress | waitress（或 gunicorn） |
| 公网 | cloudflared LaunchAgent | cloudflared systemd service |
| 前台应用检测 | `mac/frontmost/frontapp` + launchd | 服务器无桌面时**不装**；Mac 继续上报，或 Linux 桌面用 xdotool |

> 关键点：**Linux VPS 上没有“前台应用”这个概念**。如果你的 Mac 还是主力机，就让 Mac 继续跑 `mac/frontmost/pc_status_mac.sh`，把上报地址指向 Linux 服务器；Linux 只负责跑 Flask + 隧道。

## 1. 准备

以 Debian/Ubuntu 为例：

```bash
sudo apt update
sudo apt install -y python3 python3-venv git curl
```

建一个专用用户和目录：

```bash
sudo useradd --system --create-home --home-dir /opt/sleepy --shell /usr/sbin/nologin sleepy
sudo -u sleepy git clone https://github.com/<you>/sleepy.git /opt/sleepy/app
cd /opt/sleepy/app
sudo -u sleepy python3 -m venv venv
sudo -u sleepy venv/bin/pip install -r requirements.txt waitress
```

## 2. 迁移 data.json

从 Mac 拷过去（**不要提交到 git**）：

```bash
scp ~/sleepy/data.json user@server:/tmp/data.json
sudo mv /tmp/data.json /opt/sleepy/app/data.json
sudo chown sleepy:sleepy /opt/sleepy/app/data.json
sudo chmod 600 /opt/sleepy/app/data.json
```

`host` 保持 `127.0.0.1`，`port` 保持 `9010`，`secret` 不变。如果你换了 secret，记得同步改手机 MacroDroid 和 Mac 上报脚本用的那份 `data.json`。

## 3. 试运行

```bash
cd /opt/sleepy/app
sudo -u sleepy venv/bin/waitress-serve --host=127.0.0.1 --port=9010 --threads=4 server:app
```

另开一个终端：

```bash
curl -s http://127.0.0.1:9010/query
```

确认返回 JSON 后再交给 systemd。

## 4. systemd 服务

`/etc/systemd/system/sleepy.service`：

```ini
[Unit]
Description=sleepy status server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=sleepy
Group=sleepy
WorkingDirectory=/opt/sleepy/app
ExecStart=/opt/sleepy/app/venv/bin/waitress-serve --host=127.0.0.1 --port=9010 --threads=4 server:app
Restart=always
RestartSec=2
Environment=PYTHONDONTWRITEBYTECODE=1
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/sleepy/app

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sleepy
systemctl status sleepy
journalctl -u sleepy -f
```

> `ProtectHome=true` 下如果 `data.json` 不在 `/opt/sleepy/app` 会读不到；按上面的路径放即可。

## 5. Cloudflare Tunnel

### 方式 A：复用现有隧道（推荐，DNS 不用改）

在 Mac 上停掉隧道，把凭据和配置拷到 Linux：

```bash
# Mac
launchctl bootout gui/$(id -u)/com.cloudflare.sleepy-tunnel

# 拷到服务器
scp ~/.cloudflared/<TUNNEL_UUID>.json user@server:/tmp/
scp ~/.cloudflared/config.yml user@server:/tmp/
```

```bash
# Linux
sudo mkdir -p /etc/cloudflared
sudo mv /tmp/<TUNNEL_UUID>.json /etc/cloudflared/
sudo mv /tmp/config.yml /etc/cloudflared/config.yml
sudo chmod 600 /etc/cloudflared/<TUNNEL_UUID>.json

# config.yml 里 credentials-file 改成 /etc/cloudflared/<TUNNEL_UUID>.json
sudo cloudflared service install
sudo systemctl enable --now cloudflared
systemctl status cloudflared
```

同一个 tunnel 同时只能由一处 connector 健康承载；先停 Mac 再起 Linux，避免请求被分到旧机器。

### 方式 B：在 Linux 上新建隧道

```bash
curl -L -o cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb

cloudflared tunnel login
cloudflared tunnel create sleepy-linux
cloudflared tunnel route dns sleepy-linux sleep.example.com   # 会覆盖旧 CNAME
```

`~/.cloudflared/config.yml` 里 `service: http://127.0.0.1:9010`，然后 `cloudflared tunnel run sleepy-linux`。要常驻同样用 `sudo cloudflared service install`。

国内服务器从 GitHub 下载 cloudflared 可能很慢，可以换 Cloudflare 的 apt 源或让本地机器下载后 `scp` 上去。

## 6. Mac 继续上报（可选）

如果 Linux 只是换了个“机房”，Mac 仍然是你的电脑，就让 Mac 的上报直接发到公网域名。编辑 `~/Library/LaunchAgents/com.sleepy.pcstatus.plist`，在 `EnvironmentVariables` 里加：

```xml
<key>SLEEPY_SERVER</key>
<string>https://sleep.example.com</string>
```

然后：

```bash
launchctl kickstart -k gui/$(id -u)/com.sleepy.pcstatus
```

脚本里本来就有 `SERVER="${SLEEPY_SERVER:-http://127.0.0.1:9010}"`，不用改代码。Mac 上的 `com.sleepy.server` 和隧道这时可以停掉：

```bash
launchctl bootout gui/$(id -u)/com.sleepy.server
launchctl bootout gui/$(id -u)/com.cloudflare.sleepy-tunnel
```

注意 `mac/frontmost/pc_status_mac.sh` 是从本地 `data.json` 读 secret 的，两边 secret 必须一致。

## 7. 如果 Linux 本身是桌面

X11 可以用 `xdotool` 做前台检测：

```bash
sudo apt install -y xdotool
xdotool getactivewindow getwindowclassname   # 或 getwindowname
```

把 `mac/frontmost/pc_status_mac.sh` 里的 `frontapp` 换成这个命令，轮询后同样 `curl /set` 即可。Wayland 没有通用方案（GNOME 的 `Eval` 在新版本已禁用），不建议在 Wayland 桌面上折腾。

## 8. 安全

- systemd 只监听 `127.0.0.1:9010`，**不要**在防火墙/安全组放行 9010；公网只走 Cloudflare Tunnel。
- `ufw` 默认拒绝入站，只放行 SSH 即可。
- `data.json` 权限 600，不进 git。
- 定期 `sudo apt upgrade`，cloudflared 跟随官方源更新。

## 9. 迁移检查清单

- [ ] `systemctl status sleepy` 是 active (running)
- [ ] `curl http://127.0.0.1:9010/query` 正常
- [ ] `systemctl status cloudflared` 正常，日志里有 `Registered tunnel connection`
- [ ] 公网 `https://sleep.example.com/` 能打开
- [ ] 手机 `/set` 能改状态
- [ ] Mac 上报指向新地址（如果保留 Mac 作为“PC_Status”来源）
- [ ] 旧 Mac 上的 `com.sleepy.server`、`com.cloudflare.sleepy-tunnel` 已停掉，避免重复 connector
