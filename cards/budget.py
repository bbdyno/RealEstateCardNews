"""예산 × 평형대 실거래 표 — 아파트썸의 간판 형식('서울 13억대 30평대')을 매물 대신 실거래로.

  .venv/bin/python -m cards.budget 서울 10 30평대        → out/cards/서울-10억대-30평대/01.png …

한 단지 한 줄: 최근 3개월(기준월까지) 해당 평형대 마지막 실거래가가 그 억대에 드는 단지. 3년 최고가 대비, 같은 단지
최근 3개월 중위, 연차를 함께 싣는다. 구별로 묶고 한 장에 ROWS 줄씩 나눈다.
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from PIL import Image

from analytics import core
from collector import db
from web import fmt
from web.build import I3D

HERE = Path(__file__).parent
OUT = db.ROOT / "out" / "cards"
import os
import shutil
# 맥은 앱 경로, GitHub Actions(우분투)는 PATH 의 google-chrome
CHROME = os.environ.get("CHROME") or shutil.which("google-chrome") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
MAX_TABLES = 4           # 표는 4장까지(캐러셀 6장) — 넘치면 3년 거래가 많은 단지부터 싣는다


def short_name(name: str) -> str:
    """표에 싣는 단지 이름: 괄호 속 브랜드·별칭과 끝의 '아파트'를 뺀다(국토부 이름은 길다)."""
    n = re.sub(r"\(.*?\)", "", name).strip()
    n = re.sub(r"아파트$", "", n).strip()
    return n or name
ROWS = 20                # 한 장에 20줄 — 글자를 아파트썸 수준(가로폭의 약 3%)으로
MAX_ROWS = ROWS * MAX_TABLES
W, H = 1080, 1440         # 3:4 세로형(아파트썸과 같은 비율, 피드에서 가장 크게 보인다)
MIN_DEALS = 10           # 3년 매매 건수 — 세대수가 공개되지 않아 단지 규모·거래 활발함의 대리값으로 쓴다


@lru_cache(maxsize=4)
def sido_complexes(sido: str) -> tuple:
    """시도 안 모든 아파트 단지(구 이름과 함께). 같은 시도로 여러 억대·평형대를 고를 때 한 번만 읽는다."""
    c = db.connect()
    out = []
    for r in db.regions():
        if r["sido_short"] != sido:
            continue
        rows = [dict(x) for x in c.execute("SELECT * FROM deals WHERE sgg=? AND kind='apt' AND trade='sale'", (r["code"],))]
        out += [(r["name"].split()[-1], cx) for cx in core.build_complexes(rows, "apt").values()]
    return tuple(out)


def pick(sido: str, eok: int, band: str, today: dt.date) -> tuple[list[dict], str]:
    base = core.base_month(today)
    since = core.add_months(base, -2) + "-01"
    rows_out = []
    for gu, cx in sido_complexes(sido):
        live = [s for s in core.priced(cx.sales) if core.band(s["area"]) == band]
        if not live or live[0]["ymd"] < since or not (eok * 10000 <= live[0]["price"] < (eok + 1) * 10000):
            continue
        n3y = sum(1 for s in cx.sales if not s["cancelled"])
        if n3y < MIN_DEALS:
            continue
        last = live[0]
        same = [s for s in live if core.area_key(s["area"]) == core.area_key(last["area"])]
        hi = max(same, key=lambda s: s["price"])
        recent = [s["price"] for s in same if s["ymd"] >= since]
        rows_out.append({"gu": gu, "name": short_name(cx.name), "umd": cx.umd,
                         "age": (today.year - cx.build_year + 1) if cx.build_year else None,
                         "py": round(last["area"] * 1.33 / core.PY), "price": last["price"], "ymd": last["ymd"],
                         "hi": hi["price"], "vs_hi": core.change(last["price"], hi["price"]), "n3": len(recent), "n3y": n3y,
                         "is_high": last["price"] >= hi["price"] and len(same) > 1})
    # 같은 구·같은 이름(단지 번호가 갈라진 경우)은 거래가 많은 쪽 하나만
    best: dict[tuple, dict] = {}
    for x in rows_out:
        k = (x["gu"], x["name"])
        if k not in best or x["n3y"] > best[k]["n3y"]:
            best[k] = x
    rows_out = list(best.values())
    rows_out.sort(key=lambda x: (x["gu"], -x["price"]))
    return rows_out, base


def render(sido: str, eok: int, band: str, today: dt.date | None = None, rows_base=None) -> tuple[list[Path], dict]:
    today = today or dt.date.today()
    rows, base = rows_base or pick(sido, eok, band, today)
    shown = rows if len(rows) <= MAX_ROWS else sorted(sorted(rows, key=lambda x: -x["n3y"])[:MAX_ROWS],
                                                       key=lambda x: (x["gu"], -x["price"]))
    pages = [shown[i:i + ROWS] for i in range(0, len(shown), ROWS)]
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=True)
    env.filters.update(fmt.FILTERS)
    by_gu = defaultdict(int)
    for x in rows:
        by_gu[x["gu"]] += 1
    ctx = dict(sido=sido, eok=eok, band=band.replace("평대", "평형"), base=base, rows=rows, n=len(rows), pages=pages,
               n_shown=len(shown),
               total=len(pages) + 2, highs=sum(x["is_high"] for x in rows), I3D=I3D, today=today,
               logo=(db.ROOT / "web" / "static" / "logo.svg").as_uri(),
               top_gu=sorted(by_gu.items(), key=lambda kv: -kv[1])[:3],
               near_hi=sorted((x for x in rows if x["vs_hi"] is not None), key=lambda x: x["vs_hi"])[:3])
    out = OUT / f"{sido}-{eok}억대-{band}"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shots = [("cover", {}), *[("table", {"page": p, "no": i + 2}) for i, p in enumerate(pages)], ("outro", {})]
    files, overflow = [], {}
    with tempfile.TemporaryDirectory() as d:
        for k, (tpl, extra) in enumerate(shots, 1):
            html = env.get_template(f"budget_{tpl}.html").render(**ctx, **extra, idx=k)
            src = Path(d) / f"{k:02d}.html"
            src.write_text(html, encoding="utf-8")
            png = Path(d) / f"{k:02d}.png"
            common = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-sandbox", "--force-device-scale-factor=1",
                      f"--window-size={W},{H}", "--virtual-time-budget=8000"]
            subprocess.run([*common, f"--screenshot={png}", src.as_uri()], check=True, capture_output=True, timeout=120)
            dom = subprocess.run([*common, "--dump-dom", src.as_uri()], check=True, capture_output=True, text=True, timeout=120).stdout
            m = re.search(r'data-overflow="(\d+)"', dom)
            overflow[f"{k:02d}"] = int(m.group(1)) if m else 0
            jpg = out / f"{k:02d}.jpg"                       # 인스타 API 는 JPEG 만 받는다
            with Image.open(png) as im:
                im.convert("RGB").save(jpg, "JPEG", quality=92, optimize=True, progressive=True)
            files.append(jpg)
    meta = {"rows": shown, "base": base, "overflow": overflow, "ctx": {k: ctx[k] for k in ("n", "n_shown", "highs", "top_gu", "band")},
            "near_hi": ctx["near_hi"]}
    print(f"{len(rows)}개 단지 · {len(files)}장 → {out}")
    return files, meta


if __name__ == "__main__":
    sido, eok, band = (sys.argv[1:] + ["서울", "10", "30평대"][len(sys.argv[1:]):])[:3]
    render(sido, int(eok), band)
