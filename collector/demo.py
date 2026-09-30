"""개발용 가짜 데이터(demo=1). 실제 키가 없을 때 화면을 만들고 검사하는 용도로만 쓴다.

  .venv/bin/python -m collector.demo            # 넣기(이미 있으면 지우고 다시)
  .venv/bin/python -m collector.demo --clear    # 지우기 — 실데이터로 사이트를 만들기 전에 반드시

가짜라는 게 드러나도록 단지 이름에 '샘플'을 붙인다. 사이트는 demo 행이 하나라도 있으면 모든 페이지에
샘플 배너와 noindex 를 붙인다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import random

from . import db
from .normalize import with_uids

# (시군구 코드, 기준 평당가(만원, 전용 3.3㎡), 연간 추세)
REGIONS = [
    ("11680", 9800, 0.06), ("11710", 7600, 0.05), ("11440", 6200, 0.04), ("11350", 3300, 0.00),
    ("11305", 2900, -0.01), ("41135", 5600, 0.04), ("41597", 2700, -0.02), ("41287", 2300, -0.01),
    ("28185", 2800, 0.00), ("26350", 3100, 0.01), ("27260", 2700, -0.03), ("30200", 2200, 0.00),
    ("36110", 2400, 0.02), ("12330", 1500, -0.01), ("31140", 1700, 0.01), ("44133", 1500, -0.02),
    ("48123", 1400, -0.01), ("51130", 1300, 0.00), ("50110", 1900, -0.02),
]
UMD = ["중앙동", "새터동", "푸른동", "햇살동", "강변동", "산들동"]
AREAS = [(39.9, 0.08), (49.8, 0.10), (59.9, 0.34), (74.9, 0.12), (84.9, 0.30), (114.7, 0.05), (134.9, 0.01)]
STAGES = ["정비구역 지정", "추진위원회 승인", "조합설립 인가", "사업시행 인가", "관리처분 인가", "이주·철거", "착공", "준공"]


def month_list(n: int, end: dt.date) -> list[dt.date]:
    d = end.replace(day=1)
    out = []
    for _ in range(n):
        out.append(d)
        d = (d - dt.timedelta(days=1)).replace(day=1)
    return out[::-1]


def pick_area(rng: random.Random) -> float:
    return rng.choices([a for a, _ in AREAS], [w for _, w in AREAS])[0]


def gen(months: int = 36, seed: int = 7, end: dt.date | None = None) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    end = end or dt.date.today()
    ms = month_list(months, end)
    names = {r["code"]: r for r in db.regions()}
    deals: list[dict] = []
    zones: list[dict] = []
    for sgg, base, trend in REGIONS:
        region_name = names[sgg]["name"]
        n_cx = rng.randint(9, 16)
        complexes = []
        for i in range(n_cx):
            umd = rng.choice(UMD)
            year = rng.randint(1986, 2024)
            age_adj = 1.25 if year >= 2017 else (0.85 if year < 1998 else 1.0)
            complexes.append({"name": f"샘플{umd[:-1]}{i + 1}단지", "umd": umd, "jibun": str(100 + i * 7),
                              "seq": f"{sgg}-D{i:03d}", "year": year, "ppp": base * age_adj * rng.uniform(0.8, 1.2)})
        for mi, m in enumerate(ms):
            # 추세 + 2년 전쯤 한 번 꺾였다가 회복하는 흐름(신고가·전고점 대비가 생기도록)
            t = mi / 12
            level = (1 + trend) ** t * (1 - 0.08 * max(0.0, 1 - abs(mi - months * 0.35) / 6))
            last_day = ((m.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)).day
            is_current = m.year == end.year and m.month == end.month
            max_day = min(last_day, end.day) if is_current else last_day
            for cx in complexes:
                for _ in range(rng.choices([0, 1, 2, 3], [0.45, 0.35, 0.15, 0.05])[0]):
                    area = pick_area(rng)
                    ppp = cx["ppp"] * level * rng.uniform(0.93, 1.07)
                    price = int(round(area / 3.3058 * ppp / 100) * 100)
                    day = rng.randint(1, max_day)
                    deals.append(_d("apt", "sale", sgg, cx, area, m, day, rng, price=price,
                                    cancelled=1 if rng.random() < 0.02 else 0))
                for _ in range(rng.choices([0, 1, 2, 3, 4], [0.3, 0.3, 0.2, 0.12, 0.08])[0]):
                    area = pick_area(rng)
                    sale_eq = area / 3.3058 * cx["ppp"] * level
                    if rng.random() < 0.55:      # 전세
                        dep = int(round(sale_eq * rng.uniform(0.48, 0.66) / 100) * 100)
                        deals.append(_d("apt", "rent", sgg, cx, area, m, rng.randint(1, max_day), rng, deposit=dep, rent=0,
                                        contract=rng.choice(["신규", "갱신"])))
                    else:                         # 월세
                        dep = int(round(sale_eq * rng.uniform(0.08, 0.25) / 100) * 100)
                        deals.append(_d("apt", "rent", sgg, cx, area, m, rng.randint(1, max_day), rng, deposit=dep,
                                        rent=int(sale_eq * 0.0028 * rng.uniform(0.8, 1.2)), contract="신규"))
            # 오피스텔
            for j in range(4):
                cx = {"name": f"샘플오피스텔{j + 1}", "umd": UMD[j], "jibun": str(500 + j), "seq": None,
                      "year": 2008 + j * 4, "ppp": base * 0.55}
                for _ in range(rng.choices([0, 1, 2], [0.5, 0.35, 0.15])[0]):
                    area = rng.choice([19.8, 24.5, 29.7, 44.9])
                    price = int(area / 3.3058 * cx["ppp"] * level * rng.uniform(0.9, 1.1))
                    deals.append(_d("offi", "sale", sgg, cx, area, m, rng.randint(1, max_day), rng, price=price))
                for _ in range(rng.choices([0, 1, 2, 3], [0.3, 0.3, 0.25, 0.15])[0]):
                    area = rng.choice([19.8, 24.5, 29.7, 44.9])
                    sale_eq = area / 3.3058 * cx["ppp"] * level
                    if rng.random() < 0.3:
                        deals.append(_d("offi", "rent", sgg, cx, area, m, rng.randint(1, max_day), rng,
                                        deposit=int(sale_eq * rng.uniform(0.7, 0.92)), rent=0))
                    else:
                        deals.append(_d("offi", "rent", sgg, cx, area, m, rng.randint(1, max_day), rng,
                                        deposit=rng.choice([500, 1000, 2000, 3000]),
                                        rent=int(sale_eq * 0.0045 * rng.uniform(0.85, 1.15))))
            # 연립·다세대(빌라) — 대지권면적이 있어 대지지분 평당가를 낼 수 있다
            for k in range(rng.randint(2, 6)):
                umd = UMD[k % len(UMD)]
                cx = {"name": f"샘플빌라{umd[:1]}{k + 1}", "umd": umd, "jibun": f"{200 + k}-{rng.randint(1, 40)}",
                      "seq": None, "year": rng.randint(1985, 2022), "ppp": base * 0.45}
                area = rng.choice([29.9, 39.6, 49.8, 59.4])
                land = round(area * rng.uniform(0.35, 0.75), 2)
                price = int(area / 3.3058 * cx["ppp"] * level * rng.uniform(0.85, 1.15))
                deals.append(_d("rh", "sale", sgg, cx, area, m, rng.randint(1, max_day), rng, price=price, land=land,
                                house_type=rng.choice(["다세대", "연립"])))
                if rng.random() < 0.7:
                    deals.append(_d("rh", "rent", sgg, cx, area, m, rng.randint(1, max_day), rng,
                                    deposit=int(price * rng.uniform(0.6, 0.95)), rent=0, house_type="다세대"))
        # 재개발 구역(샘플)
        for z in range(rng.randint(1, 3) if sgg.startswith(("11", "41", "28", "26", "27")) else 0):
            st = rng.randint(0, 7)
            zones.append({"id": f"demo-{sgg}-{z}", "sido": names[sgg]["sido"], "sgg": sgg, "sgg_name": region_name,
                          "umd": UMD[z], "zone": f"샘플{UMD[z][:-1]}{z + 1}구역", "biz": rng.choice(["재개발", "재건축", "재개발", "모아타운"]),
                          "stage": STAGES[st], "stage_no": st, "area": round(rng.uniform(15000, 180000)),
                          "households": rng.randint(300, 3500), "address": f"{region_name} {UMD[z]} 일대",
                          "source": "샘플", "source_date": end.isoformat(), "demo": 1})
    return with_uids(deals), zones


def _d(kind, trade, sgg, cx, area, m, day, rng, *, price=None, deposit=None, rent=None, land=None,
       contract=None, house_type=None, cancelled=0) -> dict:
    return {"kind": kind, "trade": trade, "sgg": sgg, "umd": cx["umd"], "jibun": cx["jibun"], "name": cx["name"],
            "apt_seq": cx.get("seq"), "area": area, "land_area": land, "floor": rng.randint(1, 25 if kind == "apt" else 12),
            "build_year": cx["year"], "ymd": f"{m.year:04d}-{m.month:02d}-{day:02d}", "price": price,
            "deposit": deposit, "rent": rent, "contract": contract, "house_type": house_type,
            "cancelled": cancelled, "direct": 1 if rng.random() < 0.08 else 0}


ZCOLS = ("id", "sido", "sgg", "sgg_name", "umd", "zone", "biz", "stage", "stage_no", "area", "households", "address",
         "source", "source_date", "demo")


def clear(c) -> None:
    c.execute("DELETE FROM deals WHERE demo=1")
    c.execute("DELETE FROM redevelop WHERE demo=1")
    c.commit()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--clear", action="store_true")
    a = p.parse_args()
    c = db.connect()
    clear(c)
    if a.clear:
        print("샘플 데이터를 지웠습니다.")
        return
    deals, zones = gen()
    db.upsert(c, deals, demo=1)
    c.executemany(f"INSERT OR REPLACE INTO redevelop({','.join(ZCOLS)}) VALUES({','.join('?' * len(ZCOLS))})",
                  [tuple(z[k] for k in ZCOLS) for z in zones])
    c.commit()
    print(f"샘플 거래 {len(deals):,}건 · 재개발 구역 {len(zones)}곳을 넣었습니다(demo=1).")


if __name__ == "__main__":
    main()
