"""자치구 동별 대표 아파트 지도 카드. 자치구 법정동 경계 위에 동마다 대표 단지를 지시선으로 잇는다.

  .venv/bin/python -m cards.dongmap 11680 30평대     → out/cards/dong-11680-30평대/01.jpg

경계: southkorea/seoul-maps 의 서울 법정동 GeoJSON(data/geo/seoul_dong.json, 공개 데이터).
대표 아파트: 동마다 해당 평형대 최근 3개월 거래가 있는 단지 중 3년 거래가 가장 많은 단지(그 동의 '대장').
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import shutil
import sys
from pathlib import Path

from analytics import core
from collector import db

from .budget import OUT, env, shoot, short_name

GEO = db.ROOT / "data" / "geo" / "seoul_dong.json"
MAPW, MAPH = 1080, 1440


def _rings(geom) -> list[list[list[float]]]:
    """Polygon·MultiPolygon → 바깥 고리들의 좌표 목록."""
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    return [poly[0] for poly in geom["coordinates"]]


def dong_features(gu_code: str) -> list[dict]:
    g = json.loads(GEO.read_text())
    return [f for f in g["features"] if f["properties"]["EMD_CD"][:5] == gu_code]


def representatives(gu_code: str, band: str, today: dt.date) -> dict[str, dict]:
    """동(법정동명) → 대표 단지 {name, price, py}. 해당 평형대 최근 3개월 거래가 있는 단지 중 3년 거래 최다."""
    c = db.connect()
    rows = [dict(x) for x in c.execute("SELECT * FROM deals WHERE sgg=? AND kind='apt' AND trade='sale'", (gu_code,))]
    since = core.add_months(core.base_month(today), -2) + "-01"
    best: dict[str, dict] = {}
    for cx in core.build_complexes(rows, "apt").values():
        live = [s for s in core.priced(cx.sales) if core.band(s["area"]) == band]
        if not live or live[0]["ymd"] < since:
            continue
        n3y = sum(1 for s in cx.sales if not s["cancelled"])
        last = live[0]
        nm = re.sub(r"\d+동\s*[~\-]\s*\d+동$|\d+동$|\s*\d+단지$", "", short_name(cx.name)).strip()
        nm = short_name(nm) or short_name(cx.name)
        cur = best.get(cx.umd)
        if not cur or n3y > cur["n3y"]:
            best[cx.umd] = {"name": nm, "price": last["price"],
                            "py": round(last["area"] * 1.33 / core.PY), "n3y": n3y}
    return best


def build(gu_code: str, band: str, today: dt.date) -> dict:
    feats = dong_features(gu_code)
    reps = representatives(gu_code, band, today)
    # 투영: 위경도 → 지도 영역. 자치구 하나는 작아 선형 근사로 충분(경도에 cos(위도) 보정)
    pts = [pt for f in feats for ring in _rings(f["geometry"]) for pt in ring]
    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    lon0, lon1, lat0, lat1 = min(lons), max(lons), min(lats), max(lats)
    kx = math.cos(math.radians((lat0 + lat1) / 2))
    mw, mh = (lon1 - lon0) * kx, (lat1 - lat0)
    box = dict(x0=300, y0=250, w=560, h=760)                    # 지도 그리는 영역(좌우에 라벨 공간)
    s = min(box["w"] / mw, box["h"] / mh)
    offx = box["x0"] + (box["w"] - mw * s) / 2
    offy = box["y0"] + (box["h"] - mh * s) / 2

    def xy(lon, lat):
        return (offx + (lon - lon0) * kx * s, offy + (lat1 - lat) * s)

    dongs = []
    for f in feats:
        name = f["properties"]["EMD_KOR_NM"]
        paths, cxs, cys, area = [], [], [], 0
        for ring in _rings(f["geometry"]):
            pr = [xy(lon, lat) for lon, lat in ring]
            paths.append("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pr) + "Z")
            # 고리 면적·무게중심(라벨 위치용)
            a = cx = cy = 0.0
            for (x1, y1), (x2, y2) in zip(pr, pr[1:] + pr[:1]):
                cr = x1 * y2 - x2 * y1
                a += cr
                cx += (x1 + x2) * cr
                cy += (y1 + y2) * cr
            if a:
                cxs.append(cx / (3 * a))
                cys.append(cy / (3 * a))
                area += abs(a / 2)
        ci = area and max(range(len(cxs)), key=lambda i: 1)      # 가장 큰 고리 중심(단순화: 첫 중심)
        cx = sum(cxs) / len(cxs) if cxs else offx
        cy = sum(cys) / len(cys) if cys else offy
        dongs.append({"name": name, "paths": paths, "cx": cx, "cy": cy, "area": area, "rep": reps.get(name)})

    # 대표 단지가 있는 동만 라벨. 지도 중앙 기준 좌/우로 나눠 세로 정렬, 지시선으로 연결
    mid = box["x0"] + box["w"] / 2
    labeled = [d for d in dongs if d["rep"]]
    left = sorted([d for d in labeled if d["cx"] < mid], key=lambda d: d["cy"])
    right = sorted([d for d in labeled if d["cx"] >= mid], key=lambda d: d["cy"])

    def place(col, lx, anchor):
        n = len(col)
        if not n:
            return
        top, bot, gap = 300, 1180, 0
        step = (bot - top) / max(n, 1)
        for i, d in enumerate(col):
            d["lx"] = lx
            d["ly"] = top + step * i + step / 2
            d["anchor"] = anchor
    place(left, 40, "start")
    place(right, 1040, "end")
    return {"dongs": dongs, "labels": left + right, "box": box}


def gu_name(gu_code: str) -> str:
    for r in db.regions():
        if r["code"] == gu_code:
            return r["name"]
    return gu_code


def render(gu_code: str, band: str, today: dt.date | None = None) -> tuple[list[Path], dict]:
    today = today or dt.date.today()
    data = build(gu_code, band, today)
    name = gu_name(gu_code)
    ctx = dict(gu=name, band=band.replace("평대", "평형"), today=today,
               logo=(db.ROOT / "web" / "static" / "logo.svg").as_uri(),
               dongs=data["dongs"], labels=data["labels"], box=data["box"],
               n=len([d for d in data["dongs"] if d["rep"]]))
    out = OUT / f"dong-{gu_code}-{band}"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    files, overflow = shoot(env(), [("dong_map", {})], ctx, out)
    print(f"{name} {band} 대표 {ctx['n']}개 동 → {out}")
    return files, {"overflow": overflow, "n": ctx["n"]}


if __name__ == "__main__":
    a = sys.argv[1:]
    render(a[0] if a else "11680", a[1] if len(a) > 1 else "30평대")
