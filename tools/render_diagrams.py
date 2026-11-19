"""把 docs/diagrams/*.mmd 渲染为 PNG（通过 mermaid.ink 在线服务）。

用法：python tools/render_diagrams.py
依赖：能访问 https://mermaid.ink（仅渲染文档时使用，应用运行不需要联网）
"""
from __future__ import annotations

import base64
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIAGRAM_DIR = ROOT / "docs" / "diagrams"


def render(mmd_path: Path) -> Path:
    source = mmd_path.read_text(encoding="utf-8")
    payload = json.dumps({"code": source}).encode("utf-8")
    token = base64.urlsafe_b64encode(payload).decode("ascii")
    url = f"https://mermaid.ink/img/{token}?type=png&bgColor=FFFFFF"
    png_path = mmd_path.with_suffix(".png")
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as resp:
        png_path.write_bytes(resp.read())
    return png_path


def main() -> int:
    files = sorted(DIAGRAM_DIR.glob("*.mmd"))
    if not files:
        print("没有找到 .mmd 文件")
        return 1
    for path in files:
        try:
            out = render(path)
            print(f"OK  {out.relative_to(ROOT)}  ({out.stat().st_size} bytes)")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {path.name}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
