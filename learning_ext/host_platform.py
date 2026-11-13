import sys


def host_instructions():
    if sys.platform == "darwin":
        return "当前主机为 macOS，终端命令使用 zsh，使用 Unix 路径和 python3；虚拟环境解释器位于 .venv/bin/python。不要输出 Windows 的 PowerShell、winget、注册表或 .exe 操作。Mac 桌面控件读取与自动点击尚不支持，需要用户手动完成；不得声称已经执行。\n"
    if sys.platform == "win32":
        return "当前主机为 Windows，命令默认使用 PowerShell 和 Windows 路径；虚拟环境解释器位于 .venv\\Scripts\\python.exe。不要混入 Unix 命令。\n"
    return "当前主机为 Linux，命令使用 POSIX Shell 和 Unix 路径；虚拟环境解释器位于 .venv/bin/python。\n"
