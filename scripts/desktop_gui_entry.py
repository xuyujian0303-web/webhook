from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) > 1:
        from wecom_sales_webhook_bot.cli import main as cli_main

        cli_main()
        return

    from wecom_sales_webhook_bot.desktop_gui import launch_gui

    config_path = Path(sys.executable).resolve().parent / "config.local.yaml"
    launch_gui(config_path)


if __name__ == "__main__":
    main()
