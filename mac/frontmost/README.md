# macOS 前台应用检测

这个子目录只负责一件事：检测 Mac 当前的前台应用，并上报到 sleepy 的 `/set`。

- `frontapp.swift`：启动一次，读取 `NSWorkspace.shared.frontmostApplication`，打印应用名后退出。
- `pc_status_mac.sh`：每 2 秒运行一次 `frontapp`；应用名变化时调用
  `http://127.0.0.1:9010/set?secret=...&pc_status=0&pc_app_name=<App>`。
  secret 从仓库根目录的 `data.json` 读取，上报地址可用环境变量 `SLEEPY_SERVER` 覆盖。

```bash
# 直接运行（首次会自动编译 frontapp）
bash mac/frontmost/pc_status_mac.sh

# 指向远程服务器
SLEEPY_SERVER=https://sleep.example.com bash mac/frontmost/pc_status_mac.sh
```

> 不要用一个长驻的 Swift 循环读取 `NSWorkspace.frontmostApplication`：没有 RunLoop 的 CLI
> 进程会缓存进程启动时的 App，之后切换应用不会刷新。这里每次都用独立进程查询，最稳。

常驻安装见仓库根目录 `mac/install_mac.sh` 和 `README-MAC.md`。
