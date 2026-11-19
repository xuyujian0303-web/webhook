# Windows 桌面版 EXE

在安装 Python 3.12 或更新版本的 Windows 机器上，从项目根目录运行：

```powershell
.\scripts\build_windows_exe.ps1
```

生成的 `dist/企业微信销售推送.exe` 是单文件 GUI 程序。将 EXE 放在包含 `config.local.yaml`、`store_mapping.yaml` 和所选喜报模板的项目目录中再启动。配置、机构映射、模板、数据库和运行状态都保留为外部文件，不会打进 EXE。

双击 EXE 打开 GUI；GUI 启动的 `run-once` 和 `schedule` 子进程会复用同一个 EXE。开发期间仍可通过 Python 启动脚本运行。
