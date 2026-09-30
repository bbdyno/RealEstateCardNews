"""공유용 대표 이미지(web/static/og.png, 1200×630)를 만든다. 브랜드 이름을 바꾼 뒤 한 번 다시 돌린다.
맥에 설치된 Google Chrome 을 헤드리스로 써서 web/templates/og.html 을 찍는다."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))      # scripts/ 에서 바로 실행해도 web 을 찾게
from jinja2 import Environment, FileSystemLoader  # noqa: E402

from web.build import HERE, load_cfg  # noqa: E402

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def main() -> None:
    html = Environment(loader=FileSystemLoader(HERE / "templates")).get_template("og.html").render(site=load_cfg()["site"], logo=(HERE / "static" / "logo.svg").as_uri())
    out = HERE / "static" / "og.png"
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "og.html"
        src.write_text(html, encoding="utf-8")
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                        "--window-size=1200,630", "--virtual-time-budget=4000", f"--screenshot={out}", src.as_uri()],
                       check=True, capture_output=True, timeout=60)
    print(f"만들었습니다: {out} ({out.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
