"""Run one EMS read-only sale-detail query using ems_config.json.

This command is intentionally separate from the scheduler. It performs login,
the verified business initialization handshake, and one date-bounded query.
The response is written outside the repository by default.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from wecom_sales_webhook_bot.ems_source import EmsSalesDataSource


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="ems_config.json")
    parser.add_argument("--start", required=True, help="YYYYMMDD")
    parser.add_argument("--end", required=True, help="YYYYMMDD")
    parser.add_argument("--output", default=r"D:\文档\桌面\ems_sale_detail_response.bin")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    source = EmsSalesDataSource(config)
    # Keep the raw response for decoder verification without logging it.
    source.client.login(source.username, source.password)
    payload = source.client.query_sale_detail(args.start, args.end)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(f"EMS read-only query succeeded: response_bytes={len(payload)} output={output}")


if __name__ == "__main__":
    main()
