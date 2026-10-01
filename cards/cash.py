"""'현금 ○억이면 어디까지?' — 현금 + 대출 − 세금·비용으로 살 수 있는 최대 집값과, 그 값에 실제로 계약된 단지.

  .venv/bin/python -m cards.cash newlywed 서울     → out/cards/cash-newlywed-서울/01.jpg …

한 단지 한 줄: 최근 3개월 마지막 실거래가가 그 지역 최대 집값의 80~100% 인 평형 중 가장 넓은 평형.
경기는 규제지역 12곳과 나머지의 대출 규칙이 달라 시·구마다 최대 집값을 따로 계산한다.
"""
from __future__ import annotations

import datetime as dt
import shutil
import sys
from collections import defaultdict
from pathlib import Path

from analytics import core
from collector import db
from web.build import I3D

from . import loan
from .budget import MIN_DEALS, OUT, ROWS, short_name, shoot, sido_complexes, env

MAX_TABLES = 3
LOW = 0.8                # 최대 집값의 80% 이상만(예산을 거의 다 쓰는 집)

# 금액은 만원. min_area 는 전용면적(㎡) 하한 — 가구에 맞는 평형만
PERSONAS = {
    "starter":  dict(label="사회초년생", cash=10000, income=4500, first=True, min_area=33, who="1인 가구"),
    "newlywed": dict(label="신혼부부", cash=20000, income=8000, first=True, min_area=49, who="맞벌이 신혼"),
    "dual":     dict(label="맞벌이 부부", cash=30000, income=12000, first=True, min_area=59, who="아이 1명"),
    "family":   dict(label="갈아타기 가족", cash=50000, income=15000, first=False, min_area=74, who="집 팔고 무주택"),
}


def eok(v: float) -> str:
    """만원 → '5.9억' (소수 첫째 자리 버림 — 살 수 있는 값을 부풀리지 않는다)."""
    return f"{int(v / 1000) / 10:g}억"


def man(v: float) -> str:
    return f"{round(v):,}만"


def plans(p: dict, sido: str) -> dict[bool, loan.Plan]:
    """규제지역이면/아니면 각각의 최대 집값."""
    return {reg: loan.max_price(p["cash"], p["income"], reg, p["first"]) for reg in (True, False)}


def pick(key: str, sido: str, today: dt.date) -> tuple[list[dict], str, dict]:
    p = PERSONAS[key]
    pl = plans(p, sido)
    base = core.base_month(today)
    since = core.add_months(base, -2) + "-01"
    out = []
    for gu, cx in sido_complexes(sido):
        top = pl[loan.regulated(sido, gu)].price
        n3y = sum(1 for s in cx.sales if not s["cancelled"])
        if n3y < MIN_DEALS:
            continue
        sales = core.priced(cx.sales)
        best = None
        for ak in {core.area_key(s["area"]) for s in sales}:
            same = [s for s in sales if core.area_key(s["area"]) == ak]
            last = same[0]
            if last["ymd"] < since or last["area"] < p["min_area"] or not (top * LOW <= last["price"] <= top):
                continue
            if best is None or last["area"] > best[0]["area"]:
                best = (last, same)
        if not best:
            continue
        last, same = best
        hi = max(same, key=lambda s: s["price"])
        out.append({"gu": gu, "name": short_name(cx.name), "umd": cx.umd, "age": (today.year - cx.build_year + 1) if cx.build_year else None,
                    "py": round(last["area"] * 1.33 / core.PY), "area": last["area"], "price": last["price"], "ymd": last["ymd"],
                    "hi": hi["price"], "vs_hi": core.change(last["price"], hi["price"]), "n3y": n3y, "top": top,
                    "is_high": last["price"] >= hi["price"] and len(same) > 1})
    best_by: dict[tuple, dict] = {}
    for x in out:
        k = (x["gu"], x["name"])
        if k not in best_by or x["n3y"] > best_by[k]["n3y"]:
            best_by[k] = x
    rows = sorted(best_by.values(), key=lambda x: (x["gu"], -x["price"]))
    return rows, base, pl


def render(key: str, sido: str, today: dt.date | None = None, picked=None) -> tuple[list[Path], dict]:
    today = today or dt.date.today()
    p = PERSONAS[key]
    rows, base, pl = picked or pick(key, sido, today)
    limit = ROWS * MAX_TABLES
    shown = rows if len(rows) <= limit else sorted(sorted(rows, key=lambda x: -x["n3y"])[:limit], key=lambda x: (x["gu"], -x["price"]))
    pages = [shown[i:i + ROWS] for i in range(0, len(shown), ROWS)]
    by_gu = defaultdict(int)
    for x in rows:
        by_gu[x["gu"]] += 1
    reg_here = {loan.regulated(sido, x["gu"]) for x in rows} or {loan.regulated(sido, "")}
    main = pl[True] if True in reg_here else pl[False]          # 표지 큰 숫자: 규제지역이 있으면 그쪽(더 엄격)
    mixed = len(reg_here) == 2 and abs(pl[True].price - pl[False].price) >= 1000   # 규제지역 안팎 값이 실제로 다를 때만 둘로
    py_dist = defaultdict(int)
    for x in rows:
        py_dist["30평대+" if x["py"] >= 30 else "20평대" if x["py"] >= 20 else "20평 미만"] += 1
    ages = [x["age"] for x in rows if x["age"]]
    pys = defaultdict(int)
    for x in rows:
        pys[x["py"] // 10 * 10] += 1
    ctx = dict(p=p, key=key, avg_age=round(sum(ages) / len(ages)) if ages else None,
               mode_py=max(pys, key=pys.get) if pys else None, monthly=loan.monthly, sido=sido, base=base, today=today, rows=rows, n=len(rows), n_shown=len(shown), pages=pages,
               pl=pl, main=main, mixed=mixed, has_reg=True in reg_here,
               total=len(pages) + 3, I3D=I3D, eok=eok, man=man, loan=loan, rules=loan.RULES_AS_OF,
               logo=(db.ROOT / "web" / "static" / "logo.svg").as_uri(),
               top_gu=sorted(by_gu.items(), key=lambda kv: -kv[1])[:3], py_dist=py_dist,
               title=f"현금 {eok(p['cash'])}", badge=f"{sido} · {p['label']}",
               chips=[f"최대 {eok(main.price)}" + (" (규제지역)" if mixed else ""), "최근 3개월",
                      f"{today.month}.{today.day} 신고분까지"])
    out = OUT / f"cash-{key}-{sido}"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shots = [("cash_cover", {}), ("cash_calc", {"no": 2}),
             *[("budget_table", {"page": pg, "no": i + 3}) for i, pg in enumerate(pages)], ("budget_outro", {})]
    files, overflow = shoot(env(), shots, ctx, out)
    meta = {"rows": shown, "all": rows, "base": base, "overflow": overflow, "plans": pl, "main": main, "mixed": mixed,
            "top_gu": ctx["top_gu"], "n": len(rows), "n_shown": len(shown),
            "avg_age": ctx["avg_age"], "mode_py": ctx["mode_py"]}
    print(f"{len(rows)}개 단지 · {len(files)}장 → {out}")
    return files, meta


if __name__ == "__main__":
    key, sido = (sys.argv[1:] + ["newlywed", "서울"][len(sys.argv[1:]):])[:2]
    render(key, sido)
