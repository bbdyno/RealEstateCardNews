"""예산 × 평형대 실거래 표 — 아파트썸의 간판 형식('서울 13억대 30평대')을 매물 대신 실거래로.

  .venv/bin/python -m cards.budget 서울 10 30평대        → out/cards/서울-10억대-30평대/01.png …

한 단지 한 줄: 최근 3개월(기준월까지) 해당 평형대 마지막 실거래가가 그 억대에 드는 단지. 3년 최고가 대비, 같은 단지
최근 3개월 중위, 연차를 함께 싣는다. 구별로 묶고 한 장에 ROWS 줄씩 나눈다.
"""
from __future__ import annotations

import datetime as dt
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from analytics import core
from collector import db
from web import fmt
from web.build import I3D

HERE = Path(__file__).parent
OUT = db.ROOT / "out" / "cards"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
ROWS = 30
MIN_DEALS = 10           # 3년 매매 건수 — 세대수가 공개되지 않아 단지 규모·거래 활발함의 대리값으로 쓴다


def pick(sido: str, eok: int, band: str, today: dt.date) -> tuple[list[dict], str]:
    base = core.base_month(today)
    since = core.add_months(base, -2) + "-01"
    regions = [r for r in db.regions() if r["sido_short"] == sido]
    c = db.connect()
    rows_out = []
    for r in regions:
        rows = [dict(x) for x in c.execute("SELECT * FROM deals WHERE sgg=? AND kind='apt' AND trade='sale'", (r["code"],))]
        for cx in core.build_complexes(rows, "apt").values():
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
            rows_out.append({"gu": r["name"].split()[-1], "name": cx.name, "umd": cx.umd,
                             "age": (today.year - cx.build_year + 1) if cx.build_year else None,
                             "py": round(last["area"] * 1.33 / core.PY), "price": last["price"], "ymd": last["ymd"],
                             "hi": hi["price"], "vs_hi": core.change(last["price"], hi["price"]), "n3": len(recent), "n3y": n3y,
                             "is_high": last["price"] >= hi["price"] and len(same) > 1})
    rows_out.sort(key=lambda x: (x["gu"], -x["price"]))
    return rows_out, base


def render(sido: str, eok: int, band: str, today: dt.date | None = None) -> list[Path]:
    today = today or dt.date.today()
    rows, base = pick(sido, eok, band, today)
    pages = [rows[i:i + ROWS] for i in range(0, len(rows), ROWS)]
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=True)
    env.filters.update(fmt.FILTERS)
    by_gu = defaultdict(int)
    for x in rows:
        by_gu[x["gu"]] += 1
    ctx = dict(sido=sido, eok=eok, band=band.replace("평대", "평형"), base=base, rows=rows, n=len(rows), pages=pages,
               total=len(pages) + 2, highs=sum(x["is_high"] for x in rows), I3D=I3D, today=today,
               logo=(db.ROOT / "web" / "static" / "logo.svg").as_uri(),
               top_gu=sorted(by_gu.items(), key=lambda kv: -kv[1])[:3],
               near_hi=sorted((x for x in rows if x["vs_hi"] is not None), key=lambda x: x["vs_hi"])[:3])
    out = OUT / f"{sido}-{eok}억대-{band}"
    out.mkdir(parents=True, exist_ok=True)
    shots = [("cover", {}), *[("table", {"page": p, "no": i + 2}) for i, p in enumerate(pages)], ("outro", {})]
    files = []
    with tempfile.TemporaryDirectory() as d:
        for k, (tpl, extra) in enumerate(shots, 1):
            html = env.get_template(f"budget_{tpl}.html").render(**ctx, **extra, idx=k)
            src = Path(d) / f"{k:02d}.html"
            src.write_text(html, encoding="utf-8")
            png = out / f"{k:02d}.png"
            subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                            "--window-size=1080,1350", "--virtual-time-budget=6000", f"--screenshot={png}", src.as_uri()],
                           check=True, capture_output=True, timeout=90)
            files.append(png)
    print(f"{len(rows)}개 단지 · {len(files)}장 → {out}")
    return files


if __name__ == "__main__":
    sido, eok, band = (sys.argv[1:] + ["서울", "10", "30평대"][len(sys.argv[1:]):])[:3]
    render(sido, int(eok), band)
