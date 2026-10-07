"""카드 묶음(JPG)을 세로 릴스 영상(1080×1920 mp4)으로 만든다.

  .venv/bin/python -m cards.reel rank highs 서울     → out/reels/rank-highs-서울.mp4

각 카드를 세로 프레임(로고·카드·'저장하고 넘겨보기' 자막·진행 점)에 얹어 크롬으로 찍고, ffmpeg 로 이어붙인다.
장마다 조금씩 머물다 다음 장으로 부드럽게 넘어간다(표를 읽을 시간). 디자인·글꼴은 카드와 같다(같은 크롬·같은 웹폰트).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from collector import db

from .budget import CHROME

HERE = Path(__file__).parent
OUT = db.ROOT / "out" / "reels"
RW, RH = 1080, 1920
HOLD = 3.2            # 한 장을 보여주는 시간(초)
HOLD_FIRST = 2.6     # 표지
XFADE = 0.45         # 넘김 전환 시간(초)
FPS = 30


def _shoot(html: str, png: Path) -> None:
    src = png.with_suffix(".html")
    src.write_text(html, encoding="utf-8")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-sandbox",
                    "--force-device-scale-factor=1", f"--window-size={RW},{RH}", "--virtual-time-budget=8000",
                    f"--screenshot={png}", src.as_uri()], check=True, capture_output=True, timeout=120)


def frames(jpgs: list[Path], ctas: list[tuple[str, str]], d: Path) -> list[Path]:
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=True)
    tpl = env.get_template("reel_frame.html")
    logo = (db.ROOT / "web" / "static" / "logo.svg").as_uri()
    out = []
    for i, (jpg, (big, sub)) in enumerate(zip(jpgs, ctas)):
        png = d / f"f{i:02d}.png"
        _shoot(tpl.render(logo=logo, img=jpg.resolve().as_uri(), cta_big=big, cta_sub=sub,
                          idx=i, total=len(jpgs)), png)
        out.append(png)
    return out


def _holds(n: int) -> list[float]:
    return [HOLD_FIRST] + [HOLD] * (n - 1)


def video(pngs: list[Path], out_mp4: Path) -> Path:
    """각 프레임을 정해진 시간 보여주고 사이를 크로스페이드로 잇는다."""
    holds = _holds(len(pngs))
    inputs = []
    for p, h in zip(pngs, holds):
        inputs += ["-loop", "1", "-t", f"{h + XFADE:.2f}", "-i", str(p)]
    # xfade 체인: 0,1 → 2 → 3 …, offset 은 지금까지 머문 시간 합 − 전환시간
    fc, prev, off = [], "0:v", 0.0
    for i in range(1, len(pngs)):
        off += holds[i - 1] - XFADE
        tag = f"v{i}"
        fc.append(f"[{prev}][{i}:v]xfade=transition=slideleft:duration={XFADE}:offset={off:.2f}[{tag}]")
        prev = tag
    vf = f"fps={FPS},format=yuv420p"
    if len(pngs) == 1:
        filt = f"[0:v]{vf}[v]"
    else:
        fc[-1] = fc[-1].replace(f"[{prev}]", "[vx]")
        filt = ";".join(fc) + f";[vx]{vf}[v]"
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    total = sum(_holds(len(pngs)))
    subprocess.run(["ffmpeg", "-y", *inputs, "-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=r=44100:cl=stereo",
                    "-filter_complex", filt, "-map", "[v]", "-map", f"{len(pngs)}:a",
                    "-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest",
                    "-movflags", "+faststart", str(out_mp4)], check=True, capture_output=True)
    return out_mp4


# 시리즈별 자막(표지, 표, 마무리) — 몇 장이든 가운데는 같은 문구로 채운다
CTA = {
    "table":  ("저장하고 <em>천천히</em> 보기", "우리 동네·단지 있는지 확인해 보세요"),
    "mid":    ("넘겨서 <em>전체 순위</em> 보기", "단위 억 · 국토부 실거래가"),
    "end":    ("프로필 링크 → <em>jipgapradar.kr</em>", "우리 단지 층별 실거래가 검색"),
}


def ctas_for(n: int, cover: tuple[str, str]) -> list[tuple[str, str]]:
    out = [cover]
    for i in range(1, n):
        out.append(CTA["end"] if i == n - 1 else CTA["mid"] if i >= 2 else CTA["table"])
    return out


def make(jpgs: list[Path], slug: str, cover: tuple[str, str]) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        pngs = frames(jpgs, ctas_for(len(jpgs), cover), Path(d))
        return video(pngs, OUT / f"{slug}.mp4")


COVERS = {
    "budget": ("예산별 <em>실거래가</em>", "호가 아닌 실제 계약가"),
    "cash":   ("현금으로 <em>어디까지</em>", "대출까지 더한 최대 집값"),
    "rank":   ("이번 주 <em>순위</em>", "국토부 실거래 기준"),
}


def _demo(series: str, a: str, b: str) -> Path:
    import datetime as dt
    today = dt.date.today()
    if series == "rank":
        from . import rank
        files, _ = rank.render(a, b, today)
        slug, cover = f"rank-{a}-{b}", COVERS["rank"]
    elif series == "cash":
        from . import cash
        files, _ = cash.render(a, b, today)
        slug, cover = f"cash-{a}-{b}", COVERS["cash"]
    else:
        from . import budget
        files, _ = budget.render(a, int(b), "30평대", today)
        slug, cover = f"budget-{a}-{b}", COVERS["budget"]
    mp4 = make(files, slug, cover)
    print(f"{len(files)}장 · {mp4} ({mp4.stat().st_size // 1024}KB)")
    return mp4


if __name__ == "__main__":
    args = sys.argv[1:]
    _demo(args[0], args[1], args[2]) if len(args) >= 3 else print(__doc__)
