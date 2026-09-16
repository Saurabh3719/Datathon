"""Injects dashboard/data.json into dashboard/template.html to produce dashboard/index.html."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"


def main():
    data = (DASHBOARD / "data.json").read_text(encoding="utf-8")
    json.loads(data)  # validate
    template = (DASHBOARD / "template.html").read_text(encoding="utf-8")
    html = template.replace("__DASHBOARD_DATA__", data)
    (DASHBOARD / "index.html").write_text(html, encoding="utf-8")
    print(f"Wrote dashboard/index.html ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
