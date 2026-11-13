from __future__ import annotations

import re


ENVIRONMENT_RULES = """
这是网页课程，网站没有检测学习者的电脑，也不替学习者安装、执行命令或验证操作。
课程规划只说明需要什么，不代表实际环境。软件、版本、账号、插件、服务和依赖由学习者自检。
保留安装检查、创建项目、虚拟环境和实际练习，不根据网站服务器的软件状态跳过任何准备。
未指定学习者系统时明确区分 Windows、macOS、Linux 的命令，或提供不依赖系统的说明。
自行确认准备完成不代表课程已掌握，仍需练习与过关检查。
"""


def generation_context(node, topic, context):
    return "课程准备清单（供学习者自检，不是检测结果）：\n" + (context or "未提供") + ENVIRONMENT_RULES


def adapt_reading(node, topic, content):
    if not re.search(r"环境|安装|配置|准备|入门", node.title):
        return content
    notice = "> 学习准备：请在自己的电脑检查工具、版本与依赖；网站不会检测环境或执行命令。已有工具可自行核对要求后跳过重复安装，实际练习仍需完成。\n\n"
    title = re.match(r"\A# [^\n]+\n+", content)
    prefix = title.group() if title else ""
    return prefix + notice + content[len(prefix):]
