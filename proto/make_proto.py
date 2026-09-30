"""디자인 방향 비교용 단지 페이지 시안(한 파일, 세 가지 테마 전환). 실데이터로 그린다.

  .venv/bin/python proto/make_proto.py [단지명] [시군구]   → proto/complex.html
"""
from __future__ import annotations

import datetime as dt
import sys
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics import core  # noqa: E402
from collector import db  # noqa: E402
from web import charts, fmt  # noqa: E402

HERE = Path(__file__).parent


def main(name="헬리오시티", sgg="11710"):
    today = dt.date.today()
    c = db.connect()
    rows = [dict(x) for x in c.execute("SELECT * FROM deals WHERE sgg=?", (sgg,))]
    apts = core.build_complexes(rows, "apt")
    cx = next(x for x in apts.values() if x.name == name)
    region = next(r for r in db.regions() if r["code"] == sgg)
    live = core.priced(cx.sales)
    keys = defaultdict(int)
    for s in live:
        keys[core.area_key(s["area"])] += 1
    main_key = core.main_key(cx)
    cur = today.strftime("%Y-%m")
    months = [core.add_months(cur, -i) for i in range(35, -1, -1)]
    months_m = months[-24:]
    types = []
    for k in sorted(keys):
        ins = core.type_insight(cx, k, today)
        if not ins:
            continue
        top = ins["top_floor"]
        pts, by_m = [], defaultdict(list)
        for s in cx.sales:
            if core.area_key(s["area"]) != k or not s["price"]:
                continue
            cls = "x" if s["cancelled"] else "dir" if s["direct"] else "out" if s.get("outlier") else core.floor_level(s["floor"], top)
            tag = {"x": " · 해제", "dir": " · 직거래", "out": " · 확인 필요"}.get(cls, "")
            pts.append({"ym": s["ymd"][:7], "day": int(s["ymd"][8:]), "price": s["price"], "cls": cls,
                        "title": f"{s['ymd']} {s['floor']}층 {fmt.eok(s['price'])}{tag}"})
            if cls in ("lo", "mid", "hi"):
                by_m[s["ymd"][:7]].append(s["price"])
        sc = lambda ms, w, e, h: charts.scatter(pts, ms, med=[core.median(by_m.get(m, [])) for m in ms], width=w,
                                                height=h, label_every=e, fmt=fmt.eok, month_label=fmt.month)
        ins["scatter"] = f'<div class="wide">{sc(months, 720, 6, 300)}</div><div class="narrow">{sc(months_m, 360, 6, 300)}</div>'
        gq = ins["gap_q"][-12:]
        ins["gap_chart"] = charts.gap_bars(gq, width=720, height=220, fmt=fmt.eok)
        ins["gap_chart_n"] = charts.gap_bars(gq[-8:], width=360, height=220, fmt=fmt.eok)
        ins["n_all"] = keys[k]
        ins["sim"] = core.similar(cx, list(apts.values()), ins["area"], ins["now"])
        types.append(ins)
    ch = core.cancelled_highs(cx)
    env = Environment(loader=FileSystemLoader(HERE), autoescape=True, trim_blocks=True, lstrip_blocks=True)
    env.filters.update(fmt.FILTERS)
    html = env.get_template("complex.j2").render(cx=cx, r=region, types=types, main_key=main_key, ch=ch, today=today, age=fmt.age, bigsplit=fmt.big, **fmt.FILTERS)
    (HERE / "complex.html").write_text(html, encoding="utf-8")
    print("ok", len(types), "types", [len(t["sim"]) for t in types], "similar", len(ch), "cancelled highs")


if __name__ == "__main__":
    main(*sys.argv[1:])
