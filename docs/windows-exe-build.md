# Windows 桌面版 EXE

首次安装时双击项目根目录的 `一键安装并启动GUI.cmd`。脚本创建 `.venv`、安装运行/打包依赖、复制缺失配置，并构建启动桌面 GUI。要求 Python 3.12 或更新版本和网络连接；没有 Python 时会尝试用 `winget` 安装。

之后可以直接双击根目录的 `企业微信销售推送.exe`，无需 Python 环境。EXE 及扫描子进程使用同目录的配置和模板文件。若需要手动重建，在项目根目录运行：

```powershell
.\scripts\build_windows_exe.ps1
```

生成的 `企业微信销售推送.exe` 是单文件 GUI 程序。`config.local.yaml`、`ems_config.json`、`store_mapping.yaml`、`templates/` 和 `var/` 均保留在 EXE 旁，不会打进 EXE；一键脚本不会覆盖本机配置。

双击 EXE 打开 GUI；GUI 启动的 `run-once` 和 `schedule` 子进程会复用同一个 EXE。若 PyInstaller 构建失败，一键脚本会退回使用虚拟环境启动 GUI。开发期间仍可通过 Python 启动脚本运行。
