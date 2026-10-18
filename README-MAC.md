# sleepy on macOS

本分支在 [HBWuChang/sleepy](https://github.com/HBWuChang/sleepy)（上游为 [1812z/sleepy](https://github.com/1812z/sleepy)）的基础上，补充了 **macOS 部署**、**Mac 前台应用上报**、**launchd 常驻** 和 **Cloudflare Tunnel 公网部署**，并修复了原代码里的几个问题。

## 相对上游的改动

- 修复首页 500：`server.py` 里 `pc_stat['pc_desc']` / `pc_stat['pc_color']` 应为 `pc_stat['desc']` / `pc_stat['color']`，并在异常分支补上 `pc_stat` 默认值。
- `example.jsonc` 补上 `pc_status`、`pc_app_name` 字段，生成的 `data.json` 不再缺键。
- 新增 `mac/`：macOS 前台应用检测 + 上报脚本 + launchd 安装脚本。
- `/set` 日志中的 `secret` 脱敏，避免明文写进日志。
- 新增本 README。

## 原理

```
Mac: mac/frontmost/pc_status_mac.sh ──每0.5秒──> frontapp ──> /set?pc_status=0&pc_app_name=<App>
手机: MacroDroid ───────────────────────────────> /set?status=N&app_name=<App>
                                                      │
                                             Flask 写入 data.json
                                                      │
                                          首页 index.html 读取并渲染
```

服务端本身不做任何“检测”，只负责接收上报和展示。

首页每 0.5 秒轮询一次 `/query`（响应里同时包含 `info` 和 `pc_info`），状态和前台应用会自动更新，不需要手动刷新；请求失败时保留旧值，下一轮再试。

## 1. 准备环境

要求：macOS、Python ≥ 3.9、Xcode Command Line Tools（`swiftc` 用于编译前台检测器）。

```bash
xcode-select --install          # 已装可跳过
git clone https://github.com/<you>/sleepy.git
cd sleepy

python3 -m venv venv
venv/bin/pip install -r requirements.txt waitress

python3 server.py               # 首次运行会生成 data.json，看到提示后 Ctrl+C
```

> `start.py` 使用了 Python 3.10 的 `match` 语法，Python 3.9 会直接 SyntaxError；3.9 及以下请直接 `python3 server.py`。

## 2. 配置 data.json

```jsonc
{
    "debug": false,
    "host": "127.0.0.1",        // 走 Cloudflare Tunnel 时只监听本机；局域网直连可改 0.0.0.0
    "port": 9010,
    "secret": "换成随机长串",    // python3 -c "import secrets;print(secrets.token_hex(16))"
    "status": 0,
    "app_name": "系统桌面",
    "pc_status": 0,
    "pc_app_name": "系统桌面",
    "status_list": [ ... ],
    "other": { ... }
}
```

```bash
chmod 600 data.json
```

`data.json` 已在 `.gitignore` 中，**不要提交**（里面有 secret）。

## 3. 安装 launchd 常驻服务

```bash
bash mac/install_mac.sh
```

会做四件事：

1. 创建/复用 `venv` 并安装 Flask + waitress；
2. 用 `swiftc` 编译 `mac/frontmost/frontapp`；
3. 写入并加载两个 LaunchAgent：
   - `com.sleepy.server`：waitress 监听 `127.0.0.1:9010`
   - `com.sleepy.pcstatus`：每 0.5 秒上报前台应用
4. 日志输出到 `~/Library/Logs/sleepy-server.log` 和 `~/Library/Logs/sleepy-pcstatus.log`。

验证：

```bash
curl http://127.0.0.1:9010/query
launchctl print gui/$(id -u)/com.sleepy.server | grep -E "state|pid"
launchctl print gui/$(id -u)/com.sleepy.pcstatus | grep -E "state|pid"
```

> 仓库放在 `~/Documents`、`~/Downloads` 或 `~/Desktop` 下时，launchd 后台进程可能因为 macOS TCC 读不到文件（报 `Operation not permitted`）。建议把仓库放到家目录下，例如 `~/sleepy`。

## 4. Mac 前台检测是怎么做的

- `mac/frontmost/frontapp.swift`：启动一次，读取 `NSWorkspace.shared.frontmostApplication` 并打印应用名后退出。
- `mac/frontmost/pc_status_mac.sh`：每 0.5 秒运行一次 `frontapp`；应用名变化时调用：

```bash
curl -sG http://127.0.0.1:9010/set \
  --data-urlencode "secret=$SECRET" \
  --data-urlencode "pc_status=0" \
  --data-urlencode "pc_app_name=$APP"
```

为什么不用一个长驻的 Swift 循环？因为 **没有 RunLoop 的 CLI 进程里 `NSWorkspace.frontmostApplication` 会缓存进程启动时的 App**，之后切换应用不会刷新，表现为「切什么应用都显示同一个名字」。每次启动独立进程查询最稳。

目前只上报「当前前台应用」，**锁屏/睡眠不会自动显示“似了”**。如果需要，可以在脚本里加：

```bash
# CGSSessionScreenIsLocked
ioreg -n Root -d1 -a | grep -q "CGSSessionScreenIsLocked" && ...
```

或者用 `CGSessionCopyCurrentDictionary()` 判断锁屏，锁屏时发 `pc_status=1`，解锁后恢复。

### 摸鱼判断

`data.json` 里的 `pc_slack_apps` / `pc_work_apps` 是**精确匹配**（不区分大小写），`server.py` 的 `pc_display()` 会据此决定 PC 状态的颜色和描述：

| 命中 | 描述 | 颜色 |
| --- | --- | --- |
| `pc_slack_apps` | 目前 Mac 上正在使用 X，大概率在摸鱼。 | `slacking`（橙） |
| `pc_work_apps` | 目前 Mac 上正在使用 X，在认真工作。 | `working`（蓝） |
| 都不命中 | 目前 Mac 上正在使用 X。 | `awake`（绿） |

想加应用直接往数组里加名字即可（用 `frontapp` 输出的名字，例如 `终端`、`哔哩哔哩`）。注意这里只能识别**应用**，浏览器里的具体网页（比如 YouTube 标签页）识别不到，会按 Chrome / Safari 本身算中性。

页面上的名字由 `data.json` 的 `other.user` 控制（例如 `miku`）。

## 5. Cloudflare Tunnel（可选，公网访问）

```bash
brew install cloudflared
cloudflared tunnel login
cloudflared tunnel create sleepy
cloudflared tunnel route dns sleepy sleep.example.com
```

`~/.cloudflared/config.yml`：

```yaml
tunnel: <TUNNEL_UUID>
credentials-file: /Users/<you>/.cloudflared/<TUNNEL_UUID>.json

ingress:
  - hostname: sleep.example.com
    service: http://127.0.0.1:9010
  - service: http_status:404
```

```bash
cloudflared tunnel ingress validate
cloudflared tunnel run sleepy
```

常驻可以交给 launchd（示例）：

```xml
<key>ProgramArguments</key>
<array>
  <string>/opt/homebrew/bin/cloudflared</string>
  <string>--no-autoupdate</string>
  <string>--config</string>
  <string>/Users/<you>/.cloudflared/config.yml</string>
  <string>tunnel</string>
  <string>run</string>
  <string>sleepy</string>
</array>
```

建议在 Cloudflare 后台再确认：

- **SSL/TLS → Edge Certificates → Always Use HTTPS：开**
- **Network → IPv6 Compatibility：视网络情况**，国内到 Cloudflare 的 IPv6 路径不稳时可以关掉，强制走 IPv4
- 纯状态页可以关掉 **Bot Fight Mode**，避免注入 JS 检测脚本、干扰手机上报

## 6. 手机端（MacroDroid）

1. 把 `前台应用状态.macro` 传到手机，用 MacroDroid 导入；
2. 编辑其中的 HTTP 请求动作，URL 改成：

```
https://sleep.example.com/set?secret=<你的secret>&status=0&app_name={fg_app_name}
```

3. 建议再加两个宏：
   - Screen Off → `/set?secret=...&status=1`
   - Screen On → `/set?secret=...&status=0&app_name={fg_app_name}`

## 7. 访客指纹（可选，FingerprintJS）

页面通过自托管的 `static/fp.min.js`（FingerprintJS v5，MIT）计算浏览器指纹，并 POST 到 `/visit`。服务端只把摘要写进 `visits.jsonl`：

- `visitorId`、`confidence`
- 屏幕：`1440x900@2`（CSS 像素 + `devicePixelRatio`）
- 窗口大小、`platform`、`languages`、`timezone`、`User-Agent`、CPU 核心数
- Android 的 UA-CH `model`；没有 UA-CH 时（如微信 XWEB、部分华为浏览器）从 UA 的 `Android X; <model> Build/<build_id>` 提取。`Build/` 前是型号（如 `TAS-AL00`，华为 P50），后面是构建号（如 `HUAWEITAS-AL00`，华为把厂商名和型号拼在一起），两者不是一回事；页面会把构建号小字显示在型号下方。iPhone / iPad / macOS 仍然拿不到精确型号，UA 本身也可能被伪装
- 国家（`CF-IPCountry`），**不存 IP**

`/visit` 每 IP 每分钟最多 30 次，请求体上限 4KB；`visits.jsonl` 超过 5MB 自动滚动为 `visits.jsonl.1`，文件权限 600。

查看：

- 原始记录：`tail -f ~/sleepy/visits.jsonl`
- 统计页：`https://sleep.example.com/visits?secret=<你的secret>`，也可以加 `&format=json` 直接拿 JSON
- 统计页包含：总访问、独立访客、最近 14 天、屏幕/平台/国家/型号/时区分布、最近 50 条记录
- 屏幕分辨率一栏会按真实宽高比动态画一个长方形（统一缩放到 64×44 的框内，最近记录里是 26×20 的小图），所以 21:9 的带鱼屏会明显更扁，竖屏手机明显更高

`/visits` 没有公开入口，靠 `data.json` 的 `secret` 保护；secret 放在 URL 里，Cloudflare 边缘会看到，介意的话可以改成 POST 或请求头。

关闭：删掉 `templates/index.html` 底部的 `<script src="/static/fp.min.js"></script>` 和紧随其后的指纹上报脚本（以及 `privacy_note`），然后删除 `visits.jsonl`。

> 注意：浏览器指纹在 PIPL/GDPR 下通常属于个人信息。公开站点建议保留页面底部的隐私提示，并按需清理日志；不要把 `visitorId` 和 IP 拼在一起长期保存。FingerprintJS 只能识别“同一浏览器再次访问”，不等于真实身份，iPhone / Mac 的精确型号依旧拿不到。

## 8. 安全清单

- `secret` 用随机长串，不要用示例值 `MySecret`；
- 走 Tunnel 时 `host` 保持 `127.0.0.1`，不要在路由器上给 9010 做端口映射；
- 公网只暴露 HTTPS，Cloudflare 开启 Always Use HTTPS；
- `data.json`、`~/.cloudflared/` 权限 600/700；
- 不要把 `data.json`、带真实 secret 的 `.macro` 提交到仓库；
- 本分支已把 `/set` 日志里的 secret 脱敏。

## 9. 常见问题

**页面一直显示“系统桌面”**
：Mac 上报进程没跑起来，或者用了会缓存的长驻 `NSWorkspace` 循环。检查 `launchctl print gui/$(id -u)/com.sleepy.pcstatus`，并确认 `mac/frontmost/frontapp` 输出的确实是当前 App。

**域名解析不了 / 只有部分设备能打开**
：先 `dig +short sleep.example.com`，再换 `dig @1.1.1.1` 对比。路由器或代理软件的 DNS（fake-ip、自定义重写、AdGuard 过滤）可能对整域返回空记录；可临时把设备 DNS 改成 `1.1.1.1` 验证。

**页面很慢或偶发超时**
：先 `curl -4` / `curl -6` 对比；国内到 Cloudflare 洛杉矶边缘在晚高峰可能明显拥塞。可尝试关闭 Cloudflare 的 IPv6 Compatibility 或开 Argo Smart Routing。

**`/set` 返回 403 / 挑战页**
：Cloudflare Bot Fight Mode 在拦截，关掉即可。

## 10. 文件说明

| 路径 | 说明 |
| --- | --- |
| `mac/frontmost/frontapp.swift` | 单次查询前台应用并打印 |
| `mac/frontmost/pc_status_mac.sh` | 轮询并上报 `pc_status` / `pc_app_name` |
| `mac/install_mac.sh` | 安装服务端 + 上报器的 launchd 服务 |
| `mac/frontmost/README.md` | 前台检测子目录说明 |
| `server.py` | Flask 路由；已修复 `pc_desc` / `pc_color` |
| `example.jsonc` | 配置模板（含 `pc_status` / `pc_app_name`） |
| `static/fp.min.js` | FingerprintJS v5（MIT），访客指纹 |
| `templates/visits.html` | `/visits` 统计页模板 |
| `visits.jsonl` | 运行时生成的访客记录，已在 `.gitignore` |
