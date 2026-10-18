# sleepy on OpenWrt（斐讯 N1 实测）

本文记录把 sleepy 跑在 **OpenWrt 24.10 / aarch64（斐讯 N1）** 上的做法。和普通 Linux 的区别：没有 systemd、没有 pip 源、磁盘很小，而且这台机器上跑着 OpenClash。

## 环境

- OpenWrt 24.10.3，aarch64，Python 3.11（系统自带，无 pip）
- 根分区约 2GB，剩余 500MB 左右
- 已装 Docker，但拉不到镜像，所以直接用系统 Python
- 已有 OpenClash，且它默认代理“路由器自身流量”

## 1. 传文件

在 Mac 上打包（排除 venv / git / 运行时数据）：

```bash
cd ~/sleepy
tar -czf /tmp/sleepy-app.tgz \
  --exclude='./venv' --exclude='./.git' \
  --exclude='./visits.jsonl*' --exclude='./state.json*' \
  --exclude='__pycache__' --exclude='.DS_Store' \
  --exclude='./mac/frontmost/frontapp' \
  --exclude='./前台应用状态-本机.macro' .
```

OpenWrt 的 Python 3.11 没有 pip，但 Flask / waitress 都是纯 Python，可以直接把 Mac venv 里的包拷过去（排除 `.so`，MarkupSafe 会走纯 Python fallback）：

```bash
cd ~/sleepy/venv/lib/python3.9/site-packages
tar -czf /tmp/pylibs.tgz --exclude='*.so' --exclude='__pycache__' \
  flask flask-3.1.3.dist-info werkzeug werkzeug-3.1.9.dist-info \
  jinja2 jinja2-3.1.6.dist-info markupsafe markupsafe-3.0.4.dist-info \
  click click-8.1.8.dist-info itsdangerous itsdangerous-2.2.0.dist-info \
  blinker blinker-1.9.0.dist-info waitress waitress-3.0.2.dist-info \
  importlib_metadata importlib_metadata-8.7.1.dist-info zipp zipp-3.23.1.dist-info
```

```bash
scp /tmp/sleepy-app.tgz /tmp/pylibs.tgz root@192.168.5.2:/tmp/
ssh root@192.168.5.2
mkdir -p /opt/sleepy/pylibs
tar -xzf /tmp/sleepy-app.tgz -C /opt/sleepy
tar -xzf /tmp/pylibs.tgz -C /opt/sleepy/pylibs
```

`/opt/sleepy/run.py`：

```python
import sys
sys.path.insert(0, "/opt/sleepy/pylibs")
from waitress import serve
from server import app
serve(app, host="127.0.0.1", port=9010, threads=4)
```

先手动确认能跑：

```bash
cd /opt/sleepy
/usr/bin/python3 /opt/sleepy/run.py
# 另一个 SSH 窗口
curl -s http://127.0.0.1:9010/query
```

## 2. procd 服务

`/etc/init.d/sleepy`：

```sh
#!/bin/sh /etc/rc.common
USE_PROCD=1
START=95
STOP=10

start_service() {
    procd_open_instance
    procd_set_param command /bin/sh -c "cd /opt/sleepy && exec /usr/bin/python3 /opt/sleepy/run.py"
    procd_set_param respawn 3600 5 5
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
}
```

```bash
chmod +x /etc/init.d/sleepy
/etc/init.d/sleepy enable
/etc/init.d/sleepy start
netstat -ltnp | grep 9010
```

## 3. cloudflared

Mac 上从 Cloudflare 官方 apt 源取 arm64 deb（`pkg.cloudflare.com` 可访问）：

```bash
curl -L -o /tmp/cloudflared.deb \
  https://pkg.cloudflare.com/cloudflared/pool/main/c/cloudflared/cloudflared_2026.10.1_arm64.deb
shasum -a 256 /tmp/cloudflared.deb   # 与 Packages 里的 SHA256 对比
```

deb 是 ar 包，用 Python 解出 `usr/bin/cloudflared`（macOS 没有 dpkg-deb），然后 scp：

```bash
scp /tmp/cloudflared-linux-arm64 root@192.168.5.2:/usr/bin/cloudflared
ssh root@192.168.5.2 'chmod 755 /usr/bin/cloudflared && cloudflared --version'
```

把 Mac 上的隧道凭据和配置拷过去：

```bash
scp ~/.cloudflared/<TUNNEL_UUID>.json root@192.168.5.2:/etc/cloudflared/
```

`/etc/cloudflared/config.yml`：

```yaml
tunnel: <TUNNEL_UUID>
credentials-file: /etc/cloudflared/<TUNNEL_UUID>.json
protocol: quic          # 关键：N1 上 TCP 443 到边缘会被重置，QUIC 可以
edge-ip-version: "4"
ingress:
  - hostname: sleep.example.com
    service: http://127.0.0.1:9010
  - service: http_status:404
```

`/etc/init.d/cloudflared`：

```sh
#!/bin/sh /etc/rc.common
USE_PROCD=1
START=96
STOP=10

start_service() {
    procd_open_instance
    procd_set_param command /usr/bin/cloudflared --no-autoupdate --config /etc/cloudflared/config.yml tunnel run
    procd_set_param respawn 3600 5 5
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
}
```

```bash
chmod +x /etc/init.d/cloudflared
/etc/init.d/cloudflared enable
/etc/init.d/cloudflared start
logread | grep -i cloudflared | tail
```

看到 `Registered tunnel connection ... protocol=quic` 就成功了。

## 4. OpenClash 的坑（重要）

这台 N1 上 OpenClash 的 `router_self_proxy=1`，会把 **N1 自己的出站流量**也交给代理节点。当时节点全部超时，表现是：

```
[TCP] dial 主代理 ... 198.41.192.107:443 error: context deadline exceeded
```

cloudflared 于是报 `TLS handshake with edge error: EOF`，QUIC/HTTP2 都连不上。把路由器自身流量改为直连后恢复：

```bash
uci set openclash.config.router_self_proxy='0'
uci commit openclash
/etc/init.d/openclash restart
```

注意：

- 这只影响 **N1 自己**的出站流量，局域网客户端的代理规则不变；
- 直连后 TCP 443 到 Cloudflare 边缘仍可能被重置，所以 cloudflared 必须用 `protocol: quic`；
- 如果以后 OpenClash 配置被重置，记得重新设置。

## 5. Mac 端只保留上报

Mac 上的 `com.sleepy.server` 和 `com.cloudflare.sleepy-tunnel` 停掉，LaunchAgent 移到 `~/Library/LaunchAgents/disabled/`；只保留 `com.sleepy.pcstatus`，并把它指向远端：

```xml
<key>EnvironmentVariables</key>
<dict>
    <key>SLEEPY_SERVER</key>
    <string>https://sleep.example.com</string>
</dict>
```

```bash
launchctl bootout gui/$(id -u)/com.sleepy.pcstatus
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.sleepy.pcstatus.plist
```

`pc_status_mac.sh` 里的 curl 超时已放宽到 10 秒，适应公网延迟。

## 6. 验证

```bash
# N1
curl -s http://127.0.0.1:9010/query
logread | grep "Registered tunnel connection"
netstat -ltnp | grep 9010

# 任意机器
curl -s https://sleep.example.com/query
```

Mac 切换应用后，远端 `/query` 的 `pc_info.name` 应该跟着变；Mac 休眠 3 分钟后会变成「似了」（`heartbeat.pc_timeout`）。

## 7. 回滚

```bash
# N1
/etc/init.d/cloudflared stop; /etc/init.d/cloudflared disable
/etc/init.d/sleepy stop; /etc/init.d/sleepy disable

# Mac
mv ~/Library/LaunchAgents/disabled/com.sleepy.server.plist ~/Library/LaunchAgents/
mv ~/Library/LaunchAgents/disabled/com.cloudflare.sleepy-tunnel.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.sleepy.server.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cloudflare.sleepy-tunnel.plist
# 并把 pcstatus 的 SLEEPY_SERVER 改回 http://127.0.0.1:9010
```

## 8. 注意

- 应用和 cloudflared 都以 root 跑，OpenWrt 上比较常见；`/etc/cloudflared/*.json` 权限 600，`data.json` 600。
- 根分区只有 2GB，不要把 venv、pip 缓存、大日志放上去；`visits.jsonl` 超过 5MB 会自动滚动。
- 升级 Flask/waitress 时，在 Mac venv 里升级后按第 1 步重新打包 `pylibs`；不要直接在 N1 上 `pip install`（没有 pip，而且外网不稳）。
