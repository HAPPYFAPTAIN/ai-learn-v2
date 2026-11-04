# 官网资料预览

官网隔离 worker 使用系统安装的 LibreOffice Writer 转换 Word/ODT/RTF，用 Poppler `pdftoppm` 渲染 PDF；图片预览使用 Pillow。引擎在运行时环境安装，不把 EXE、DLL 或整套桌面预览引擎提交到 Git。系统依赖见 `runtime/apt-packages.txt`。

转换使用独立临时配置、超时和进程退出检查；预览缓存在当前账号数据目录，原件保持不变。最多预览100MiB文件及4000万像素图片。详细边界以 `learning_ext/document_preview.py` 为准。

浏览器的 PDF.js viewer 和 worker 文件由 `learning_ext/app.py` 及组件动态导入加载，仍是运行依赖。压缩/带哈希的文件名不代表无用构建垃圾。字体、D3、Markmap、Tribute、MiniSearch 同样按实际引用保留，许可证随资源发布。

上游 Windows 预览分支仍在共享模块中，但便携引擎组装脚本和 Windows 打包入口已移回上游维护。本仓库不分发 Windows 软件包。
