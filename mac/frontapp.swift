// 读取当前前台应用的名称。每次运行都是独立进程，避免 NSWorkspace 在长驻进程里缓存旧值。
import AppKit
let name = NSWorkspace.shared.frontmostApplication?.localizedName ?? ""
print(name)
