"""로고(web/static/logo.svg)로 PNG 아이콘을 만든다: apple-touch-icon(180), icon-512, 인스타 프로필(1080, 모서리 없음).
맥에 설치된 Google Chrome 을 헤드리스로 쓴다. 로고를 바꾸면 한 번 다시 돌린다."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "web" / "static"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
JOBS = [("logo.svg", "apple-touch-icon.png", 180), ("logo.svg", "icon-512.png", 512),
        ("logo-square.svg", "instagram-profile.png", 1080)]


def main() -> None:
    for src, out, size in JOBS:
        svg = (STATIC / src).read_text(encoding="utf-8")
        html = (f'<html><body style="margin:0;background:transparent">'
                f'<div style="width:{size}px;height:{size}px">{svg.replace("<svg ", f"<svg width=\"{size}\" height=\"{size}\" ", 1)}</div></body></html>')
        with tempfile.TemporaryDirectory() as d:
            page = Path(d) / "icon.html"
            page.write_text(html, encoding="utf-8")
            subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                            "--default-background-color=00000000", f"--window-size={size},{size}",
                            f"--screenshot={STATIC / out}", page.as_uri()], check=True, capture_output=True, timeout=60)
        print(f"{out} {size}px ({(STATIC / out).stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
