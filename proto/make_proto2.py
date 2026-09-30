"""단지 페이지 시안 v2(아파트썸식 표·숫자 그래프 + 컬러 타일 + 3D 아이콘). → proto/complex2.html

  .venv/bin/python proto/make_proto2.py [단지명] [시군구]
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
FLUENT = "https://cdn.jsdelivr.net/gh/microsoft/fluentui-emoji@main/assets/{}/3D/{}_3d.png"
ICONS = {k: FLUENT.format(n.replace(" ", "%20"), n.lower().replace(" ", "_")) for k, n in {
    "house": "House", "offi": "Office building", "villa": "Houses", "redev": "Building construction", "up": "Chart increasing",
    "down": "Chart decreasing", "budget": "Money bag", "rank": "Trophy", "fire": "Fire", "key": "Key", "warn": "Warning",
    "gap": "Money with wings", "pin": "Round pushpin", "search": "Magnifying glass tilted left", "compare": "Balance scale",
    "chart": "Bar chart", "elevator": "Elevator", "coin": "Coin", "cal": "Spiral calendar", "city": "Cityscape",
    "receipt": "Receipt", "bulb": "Light bulb"}.items()}


def quarter(ymd):
    return f"{ymd[2:4]}년 {(int(ymd[5:7]) - 1) // 3 + 1}분기"


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
    # 최근 4개 분기
    qs = []
    m = cur
    while len(qs) < 4:
        q = quarter(m + "-01")
        if q not in qs:
            qs.append(q)
        m = core.add_months(m, -1)
    qs = qs[::-1]
    table = []
    for k in sorted(keys):
        ss = [s for s in live if core.area_key(s["area"]) == k]
        byq = defaultdict(list)
        for s in ss:
            byq[quarter(s["ymd"])].append(s["price"])
        hi = max(ss, key=lambda s: s["price"])
        cells = [(core.median(byq[q]) if byq[q] else None, len(byq[q])) for q in qs]
        last = next((v for v, _ in reversed(cells) if v), None)
        table.append({"key": k, "area": ss[0]["area"], "cells": cells, "hi": hi,
                      "at_high": bool(last and last >= hi["price"] * 0.995)})
    types = []
    months = [core.add_months(cur, -i) for i in range(23, -1, -1)]
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
            pts.append({"ym": s["ymd"][:7], "day": int(s["ymd"][8:]), "price": s["price"], "cls": cls,
                        "title": f"{s['ymd']} {s['floor']}층 {fmt.eok(s['price'])}"})
            if cls in ("lo", "mid", "hi"):
                by_m[s["ymd"][:7]].append(s["price"])
        vals = [core.median(by_m.get(m, [])) for m in months]
        cnts = [len(by_m.get(m, [])) for m in months]
        lab = [fmt.month(m) for m in months]
        ins["line"] = charts.labeled_line(vals, lab, counts=cnts, width=680, height=250, fmt=fmt.eok, label_every=3, tick_every=3)
        ins["line_n"] = charts.labeled_line(vals[-12:], lab[-12:], counts=cnts[-12:], width=360, height=240, fmt=fmt.eok,
                                            label_every=2, tick_every=2)
        ins["scatter"] = charts.scatter(pts, months, med=vals, width=680, height=250, label_every=3, fmt=fmt.eok, month_label=fmt.month)
        ins["scatter_n"] = charts.scatter(pts, months[-12:], med=vals[-12:], width=360, height=240, label_every=2, fmt=fmt.eok,
                                          month_label=fmt.month)
        gq = ins["gap_q"][-8:]
        ins["gap_chart"] = charts.gap_bars(gq, width=680, height=200, fmt=fmt.eok)
        ins["gap_chart_n"] = charts.gap_bars(gq[-6:], width=360, height=200, fmt=fmt.eok)
        ins["n_all"] = keys[k]
        ins["sim"] = core.similar(cx, list(apts.values()), ins["area"], ins["now"])
        # 최근 거래(신고가 표시)
        best, flags = 0, {}
        for s in sorted([s for s in cx.sales if core.area_key(s["area"]) == k and s["price"]], key=lambda s: s["ymd"]):
            if not s["cancelled"] and not s["direct"] and not s.get("outlier"):
                if best and s["price"] > best:
                    flags[id(s)] = "신고가"
                best = max(best, s["price"])
        ins["recent"] = [dict(s, flag=flags.get(id(s))) for s in cx.sales if core.area_key(s["area"]) == k][:12]
        fv = [f["median"] for f in ins["floors"]]
        lo_f, hi_f = min(fv, default=0), max(fv, default=0)
        for f in ins["floors"]:      # 차이가 보이게: 가장 싼 층을 40%, 가장 비싼 층을 100% 로
            f["w"] = 40 + 60 * (f["median"] - lo_f) / (hi_f - lo_f) if hi_f > lo_f else 70
        types.append(ins)
    ch = core.cancelled_highs(cx)
    env = Environment(loader=FileSystemLoader(HERE), autoescape=True, trim_blocks=True, lstrip_blocks=True)
    env.filters.update(fmt.FILTERS)
    html = env.get_template("complex2.j2").render(cx=cx, r=region, types=types, main_key=main_key, ch=ch, table=table, qs=qs,
                                                   today=today, age=fmt.age, bigsplit=fmt.big, I=ICONS, **fmt.FILTERS)
    (HERE / "complex2.html").write_text(html, encoding="utf-8")
    print("ok", len(types), len(table), len(ch))


if __name__ == "__main__":
    main(*sys.argv[1:])
