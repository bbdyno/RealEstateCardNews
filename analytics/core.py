"""시군구 하나의 거래로 페이지에 필요한 숫자를 만든다. 사이트 빌드는 시군구마다 이걸 한 번씩 부른다.

정의(화면에도 같은 말로 적는다)
- 기준월: 계약 뒤 30일 안에 신고하므로 최근 달은 덜 모여 있다. 월말에서 21일이 지난 가장 최근 달을 기준월로 삼고,
  그 뒤 달은 '집계 중'으로 표시한다. 비교(전월·전년 대비)는 기준월끼리만 한다.
- 평당가: 국토부는 전용면적만 준다. 모든 평당가는 '전용 3.3㎡당'이다.
- 신고가: 수집 기간(기본 3년) 안의 같은 단지·같은 면적 최고가를 넘은 거래. '3년 내 최고가'로 적는다.
- 해제된 거래는 통계에서 빼고, 거래 이력에만 '해제'로 보여 준다.
- 직거래(가족 간 거래 등)는 거래량에는 넣고 가격 통계에서는 뺀다. 이력에는 '직거래'로 보여 준다.
- 이상 거래: 같은 단지·같은 면적에서 1년 안에 ±12% 이내 가격의 다른 거래가 없고, 나머지 거래 중위값과 20% 넘게
  다르면 '확인 필요'로 보고 가격 통계에서 뺀다(신고 오류·특수 거래로 최고가·하락률이 튀는 것을 막는다).
- 금액 단위는 만원.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

PY = 3.3058          # 1평(㎡)
REPORT_LAG_DAYS = 21


# ── 작은 도구 ──────────────────────────────────────────────────────────────

def median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def ppp(price, area):
    """전용 3.3㎡당 가격(만원)."""
    return price / (area / PY) if price and area else None


def change(now, before):
    return (now / before - 1) if now and before else None


def month_key(ymd: str) -> str:
    return ymd[:7]


def add_months(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    i = y * 12 + (m - 1) + n
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def base_month(today: dt.date) -> str:
    """월말에서 REPORT_LAG_DAYS 가 지난 가장 최근 달(YYYY-MM)."""
    d = today.replace(day=1) - dt.timedelta(days=1)          # 지난달 말일
    while d + dt.timedelta(days=REPORT_LAG_DAYS) > today:
        d = d.replace(day=1) - dt.timedelta(days=1)
    return d.strftime("%Y-%m")


def band(area: float | None) -> str | None:
    """전용면적 → 흔히 부르는 평형대. 국토부는 공급면적을 주지 않아 전용률 75%를 가정해 어림한다."""
    if not area:
        return None
    if area < 50:
        return "10평대"
    if area < 75:
        return "20평대"
    if area < 100:
        return "30평대"
    if area < 125:
        return "40평대"
    return "50평대 이상"


# 경계는 공급 평형 어림(전용 × 1.33 ÷ 3.3058)이 20·30·40·50평이 되는 전용면적(약 50·75·100·125㎡)
BAND_HINT = {"10평대": "전용 50㎡ 미만", "20평대": "전용 50~75㎡(59㎡형)", "30평대": "전용 75~100㎡(84㎡형)",
             "40평대": "전용 100~125㎡", "50평대 이상": "전용 125㎡ 이상"}
BANDS = list(BAND_HINT)


def area_key(area: float | None) -> int | None:
    """같은 타입을 묶는 면적 키(84.97·84.99 → 85)."""
    return round(area) if area else None


def short_id(*parts) -> str:
    return "h" + hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:10]


# ── 결과 구조 ──────────────────────────────────────────────────────────────

@dataclass
class Complex:
    cid: str
    kind: str                     # apt / offi
    sgg: str
    umd: str
    jibun: str
    name: str
    build_year: int | None = None
    sales: list = field(default_factory=list)      # 해제 포함, 최신순
    rents: list = field(default_factory=list)
    # 계산값
    last_sale: dict | None = None
    peak: dict | None = None          # 같은 면적 기준 최고가 거래(최근 거래의 면적)
    drop: float | None = None         # 최근 거래가 / 최고가 - 1
    jeonse_ratio: float | None = None
    yield_: float | None = None       # 오피스텔 월세 수익률
    median_rent: dict | None = None
    series: list = field(default_factory=list)     # [(YYYY-MM, 중위 평당가, 거래 수)]
    by_band: dict = field(default_factory=dict)    # 평형대 → {last, peak, drop, n}


# ── 계산 ──────────────────────────────────────────────────────────────────

def _cx_key(r) -> tuple:
    """단지를 가르는 키. 전월세에는 단지 번호가 없어 이 키로 매매와 잇는다 — 띄어쓰기 차이로 갈라지지 않게 공백은 무시한다."""
    return (r["kind"], (r["umd"] or "").replace(" ", ""), (r["jibun"] or "").replace(" ", ""),
            (r["name"] or "").replace(" ", ""))


def build_complexes(rows, kind: str) -> dict[str, Complex]:
    """아파트·오피스텔 단지별로 거래를 묶는다. 아파트 전월세에는 단지 일련번호가 없어 (동·지번·이름)으로 매매와 잇는다."""
    seq_of: dict[tuple, str] = {}
    for r in rows:
        if r["kind"] == kind and r["trade"] == "sale" and r["apt_seq"]:
            seq_of[_cx_key(r)] = r["apt_seq"]
    out: dict[str, Complex] = {}
    for r in rows:
        if r["kind"] != kind or not r["name"]:
            continue
        key = _cx_key(r)
        cid = r["apt_seq"] or seq_of.get(key) or short_id(r["sgg"], *key)
        cx = out.get(cid)
        if cx is None:
            cx = out[cid] = Complex(cid=cid, kind=kind, sgg=r["sgg"], umd=r["umd"] or "", jibun=r["jibun"] or "",
                                    name=r["name"])
        if r["build_year"]:
            cx.build_year = r["build_year"]
        (cx.sales if r["trade"] == "sale" else cx.rents).append(dict(r))
    for cx in out.values():
        cx.sales.sort(key=lambda d: d["ymd"], reverse=True)
        cx.rents.sort(key=lambda d: d["ymd"], reverse=True)
        _fill(cx)
    return out


OUTLIER_BAND = 0.12      # 이 안의 가격이면 서로 '받쳐 주는' 거래
OUTLIER_DEV = 0.20       # 받쳐 주는 거래 없이 이만큼 벗어나면 이상 거래
OUTLIER_DAYS = 365


def _day(s) -> int:
    if "_d" not in s:
        s["_d"] = dt.date.fromisoformat(s["ymd"]).toordinal()
    return s["_d"]


def flag_outliers(sales: list[dict]) -> None:
    """같은 면적 거래가 3건 이상일 때만 판단한다. 1년 안에 ±12% 이내 거래가 하나라도 있으면 정상으로 본다."""
    groups = defaultdict(list)
    for x in sales:
        groups[area_key(x["area"])].append(x)
    for g in groups.values():
        if len(g) < 3:
            continue
        for x in g:
            others = [o for o in g if o is not x]
            near = [o for o in others if abs(_day(o) - _day(x)) <= OUTLIER_DAYS]
            if any(abs(o["price"] / x["price"] - 1) <= OUTLIER_BAND for o in near):
                continue
            base = median(o["price"] for o in (near if len(near) >= 2 else others))
            if base and abs(x["price"] / base - 1) > OUTLIER_DEV:
                x["outlier"] = 1


def priced(sales: list[dict]) -> list[dict]:
    """가격 통계에 쓰는 매매: 해제·직거래·이상 거래를 뺀다."""
    return [x for x in sales if not x["cancelled"] and x["price"] and not x["direct"] and not x.get("outlier")]


def _fill(cx: Complex) -> None:
    flag_outliers([x for x in cx.sales if not x["cancelled"] and x["price"] and not x["direct"]])
    live = priced(cx.sales)
    if live:
        cx.last_sale = live[0]
        same = [s for s in live if area_key(s["area"]) == area_key(cx.last_sale["area"])]
        cx.peak = max(same, key=lambda s: s["price"])
        cx.drop = change(cx.last_sale["price"], cx.peak["price"])
    for b in BANDS:
        sb = [s for s in live if band(s["area"]) == b]
        if sb:
            pk = max(sb, key=lambda s: s["price"])
            cx.by_band[b] = {"last": sb[0], "peak": pk, "drop": change(sb[0]["price"], pk["price"]), "n": len(sb)}
    # 월별 중위 평당가
    by_m = defaultdict(list)
    for s in live:
        by_m[month_key(s["ymd"])].append(ppp(s["price"], s["area"]))
    cx.series = [(m, median(v), len(v)) for m, v in sorted(by_m.items())]
    # 전세가율: 최근 12개월, 같은 평형대끼리 (전세 중위 / 매매 중위)
    if live:
        horizon = add_months(month_key(live[0]["ymd"]), -12)
        ratios = []
        for b in BANDS:
            sp = [s["price"] for s in live if band(s["area"]) == b and month_key(s["ymd"]) >= horizon]
            jd = [r["deposit"] for r in cx.rents if band(r["area"]) == b and r["rent"] == 0 and r["deposit"]
                  and month_key(r["ymd"]) >= horizon]
            if sp and jd:
                ratios.append(median(jd) / median(sp))
        cx.jeonse_ratio = median(ratios)
    # 오피스텔 수익률: 연 월세 / (매매가 - 월세 보증금), 최근 12개월 중위값
    if cx.kind == "offi" and live:
        horizon = add_months(month_key(live[0]["ymd"]), -12)
        wol = [r for r in cx.rents if r["rent"] and month_key(r["ymd"]) >= horizon]
        price = median([s["price"] for s in live if month_key(s["ymd"]) >= horizon])
        if wol and price:
            rent, dep = median([r["rent"] for r in wol]), median([r["deposit"] or 0 for r in wol])
            if price > dep:
                cx.yield_ = rent * 12 / (price - dep)
                cx.median_rent = {"rent": rent, "deposit": dep, "n": len(wol)}


def new_highs(complexes: dict[str, Complex], since: str) -> list[dict]:
    """since(YYYY-MM-DD) 이후 거래 중, 같은 단지·같은 면적의 이전 최고가를 넘은 것. 이전 거래가 있어야 신고가로 친다."""
    out = []
    for cx in complexes.values():
        live = sorted(priced(cx.sales), key=lambda s: s["ymd"])
        best: dict[int, int] = {}
        for s in live:
            k = area_key(s["area"])
            prev = best.get(k)
            if prev is not None and s["price"] > prev and s["ymd"] >= since:
                out.append({"cx": cx, "deal": s, "prev": prev, "up": s["price"] / prev - 1})
            if prev is None or s["price"] > prev:
                best[k] = s["price"]
    out.sort(key=lambda h: h["deal"]["ymd"], reverse=True)
    return out


@dataclass
class RegionStats:
    sgg: str
    base: str                                      # 기준월
    months: list = field(default_factory=list)     # [(YYYY-MM, 거래 수, 중위 평당가, 집계중 여부)] 최근 24개월
    count_base: int = 0
    count_prev: int | None = None
    count_yoy: int | None = None
    median_price: float | None = None              # 최근 3개월(기준월까지) 중위 매매가
    median_ppp: float | None = None
    ppp_change: float | None = None                # 직전 3개월 대비
    jeonse_ratio: float | None = None
    highs: int = 0


def region_stats(rows, kind: str, today: dt.date, complexes: dict[str, Complex] | None = None) -> RegionStats:
    base = base_month(today)
    live = [r for r in rows if r["kind"] == kind and r["trade"] == "sale" and not r["cancelled"] and r["price"]]
    by_m = defaultdict(list)          # 거래량(직거래 포함)
    px_m = defaultdict(list)          # 가격 통계(직거래 제외)
    for r in live:
        by_m[month_key(r["ymd"])].append(r)
        if not r["direct"]:
            px_m[month_key(r["ymd"])].append(r)
    cur = today.strftime("%Y-%m")
    months = []
    m = add_months(cur, -23)
    while m <= cur:
        v = by_m.get(m, [])
        months.append((m, len(v), median(ppp(r["price"], r["area"]) for r in px_m.get(m, [])), m > base))
        m = add_months(m, 1)
    st = RegionStats(sgg=rows[0]["sgg"] if rows else "", base=base, months=months)
    st.count_base = len(by_m.get(base, []))
    st.count_prev = len(by_m.get(add_months(base, -1), []))
    st.count_yoy = len(by_m.get(add_months(base, -12), []))
    w3 = [r for mm in (base, add_months(base, -1), add_months(base, -2)) for r in px_m.get(mm, [])]
    p3 = [r for mm in (add_months(base, -3), add_months(base, -4), add_months(base, -5)) for r in px_m.get(mm, [])]
    st.median_price = median(r["price"] for r in w3)
    st.median_ppp = median(ppp(r["price"], r["area"]) for r in w3)
    st.ppp_change = change(st.median_ppp, median(ppp(r["price"], r["area"]) for r in p3))
    if complexes:
        st.jeonse_ratio = median(cx.jeonse_ratio for cx in complexes.values() if cx.jeonse_ratio)
    return st


def villa_by_dong(rows, today: dt.date) -> list[dict]:
    """연립·다세대 매매를 동별로: 대지지분 평당가(매매가 ÷ 대지권면적 평) 중위값, 분기별 흐름, 최근 거래 목록."""
    base = base_month(today)
    horizon = add_months(base, -11)
    by_dong = defaultdict(list)
    rents = defaultdict(list)
    for r in rows:
        if r["kind"] != "rh" or r["cancelled"]:
            continue
        if r["trade"] == "sale" and r["price"]:
            by_dong[r["umd"]].append(r)
        elif r["trade"] == "rent" and r["rent"] == 0 and r["deposit"]:
            rents[(r["umd"], r["jibun"], r["name"])].append(r["deposit"])
    out = []
    for umd, deals in by_dong.items():
        recent = [d for d in deals if month_key(d["ymd"]) >= horizon]
        land = [d["price"] / (d["land_area"] / PY) for d in recent if d["land_area"]]
        q = defaultdict(list)
        for d in deals:
            if d["land_area"]:
                y, mo = int(d["ymd"][:4]), int(d["ymd"][5:7])
                q[f"{y} {(mo - 1) // 3 + 1}Q"].append(d["price"] / (d["land_area"] / PY))
        # 전세가율(같은 건물 전세 중위 ÷ 매매 중위) — 계약 전 확인할 곳을 찾는 참고값
        bld = defaultdict(list)
        for d in recent:
            bld[(d["umd"], d["jibun"], d["name"])].append(d["price"])
        high_ratio = []
        for k, prices in bld.items():
            if rents.get(k):
                ratio = median(rents[k]) / median(prices)
                if ratio >= 0.8:
                    high_ratio.append({"jibun": k[1], "name": k[2], "ratio": ratio})
        out.append({
            "umd": umd, "n": len(recent), "land_ppp": median(land), "price": median(d["price"] for d in recent),
            "quarters": [(k, median(v), len(v)) for k, v in sorted(q.items())],
            "recent": sorted(deals, key=lambda d: d["ymd"], reverse=True)[:30],
            "high_ratio": sorted(high_ratio, key=lambda h: -h["ratio"])[:10],
        })
    out.sort(key=lambda v: -(v["n"] or 0))
    return out


# ── 단지 페이지 심화(호갱노노에 없는 것들) ─────────────────────────────────────

def main_key(cx: Complex) -> int | None:
    """거래가 가장 많은 면적 타입(84.97 → 85). 단지 페이지의 기본 탭."""
    live = priced(cx.sales)
    if not live:
        return None
    cnt = defaultdict(int)
    for s in live:
        cnt[area_key(s["area"])] += 1
    return max(cnt, key=lambda k: (cnt[k], k))


def floor_level(floor: int | None, top: int) -> str:
    """층을 단지 최고층 기준 3등분(저·중·고). 동별 층수는 공개되지 않아 단지에서 거래된 가장 높은 층을 건물 높이로 본다."""
    if not floor or top < 6:
        return "mid"
    if floor <= max(3, top / 3):
        return "lo"
    return "hi" if floor > top * 2 / 3 else "mid"


def type_insight(cx: Complex, key: int, today: dt.date) -> dict | None:
    """면적 타입 하나에 대한 '지금 얼마·어디쯤·몇 층이 비싼가·갭은 얼마' 요약."""
    live = [s for s in priced(cx.sales) if area_key(s["area"]) == key]
    if not live:
        return None
    top = max((s["floor"] or 0) for s in cx.sales) or 0
    cur = today.strftime("%Y-%m")
    h3, h12 = add_months(cur, -3), add_months(cur, -12)
    recent = [s for s in live if month_key(s["ymd"]) > h3] or live[:3]
    now = median(s["price"] for s in recent)
    lo, hi = min(live, key=lambda s: s["price"]), max(live, key=lambda s: s["price"])
    span = hi["price"] - lo["price"]
    out = {"key": key, "area": live[0]["area"], "n": len(live), "now": now, "now_n": len(recent),
           "now_basis": "최근 3개월 중위" if month_key(recent[0]["ymd"]) > h3 else "최근 3건 중위",
           "last3": live[:3], "lo": lo, "hi": hi, "pos": (now - lo["price"]) / span if span else None,
           "from_hi": change(now, hi["price"]), "from_lo": change(now, lo["price"])}
    # 층별: 최근 24개월(부족하면 전체) 저·중·고층 중위가와 중층 대비 차이
    pool = [s for s in live if month_key(s["ymd"]) > add_months(cur, -24)]
    pool = pool if len(pool) >= 9 else live
    lv = defaultdict(list)
    for s in pool:
        lv[floor_level(s["floor"], top)].append(s["price"])
    mid = median(lv["mid"]) if len(lv["mid"]) >= 3 else None
    out["floors"] = [{"lv": k, "label": {"lo": "저층", "mid": "중층", "hi": "고층"}[k], "median": median(lv[k]),
                      "n": len(lv[k]), "vs_mid": change(median(lv[k]), mid) if k != "mid" and len(lv[k]) >= 3 else None}
                     for k in ("lo", "mid", "hi") if lv[k]]
    out["top_floor"] = top
    # 전세: 신규 계약만(갱신은 5% 상한이 걸려 시세가 아니다). 갭 = 매매 − 신규 전세, 최근 12개월
    jr = [r for r in cx.rents if area_key(r["area"]) == key and r["rent"] == 0 and r["deposit"]
          and month_key(r["ymd"]) > h12]
    new = [r["deposit"] for r in jr if r["contract"] != "갱신"]
    renew = [r["deposit"] for r in jr if r["contract"] == "갱신"]
    s12 = [s["price"] for s in live if month_key(s["ymd"]) > h12]
    out["jeonse_new"] = median(new) if len(new) >= 2 else None
    out["jeonse_renew"] = median(renew) if len(renew) >= 2 else None
    out["jeonse_n"] = (len(new), len(renew))
    sp = median(s12)
    out["gap"] = sp - out["jeonse_new"] if sp and out["jeonse_new"] else None
    out["jratio_new"] = out["jeonse_new"] / sp if sp and out["jeonse_new"] else None
    # 분기별 갭 흐름
    q = defaultdict(lambda: ([], []))
    for s in live:
        q[_quarter(s["ymd"])][0].append(s["price"])
    for r in cx.rents:
        if area_key(r["area"]) == key and r["rent"] == 0 and r["deposit"] and r["contract"] != "갱신":
            q[_quarter(r["ymd"])][1].append(r["deposit"])
    out["gap_q"] = [(k, median(a) - median(b) if a and b else None, median(a), median(b)) for k, (a, b) in sorted(q.items())]
    return out


def _quarter(ymd: str) -> str:
    return f"{ymd[2:4]}.{(int(ymd[5:7]) - 1) // 3 + 1}Q"


def cancelled_highs(cx: Complex) -> list[dict]:
    """해제된 거래 중 계약 당시 같은 면적 3년 내 최고가를 넘었던 것 — '신고가 찍고 해제'(집값 띄우기 의심 신호)."""
    by_key = defaultdict(list)
    for s in cx.sales:
        if s["price"] and not s["direct"]:
            by_key[area_key(s["area"])].append(s)
    out = []
    for g in by_key.values():
        g = sorted(g, key=lambda s: s["ymd"])
        best = None
        for s in g:
            if s["cancelled"]:
                if best and s["price"] > best:
                    out.append({"deal": s, "prev": best, "up": s["price"] / best - 1})
            elif not s.get("outlier"):
                best = max(best or 0, s["price"])
    return sorted(out, key=lambda h: h["deal"]["ymd"], reverse=True)


def similar(cx: Complex, pool: list[Complex], area: float, price: float, n: int = 6) -> list[dict]:
    """같은 시군구에서 같은 평형대 최근 거래가가 price 의 ±12% 안인 다른 단지 — '이 돈이면 여기도'. 가까운 가격 순."""
    b = band(area)
    out = []
    for o in pool:
        if o.cid == cx.cid or o.kind != cx.kind or b not in o.by_band:
            continue
        last = o.by_band[b]["last"]
        d = last["price"] / price - 1
        if abs(d) <= 0.12:
            out.append({"cx": o, "deal": last, "diff": d})
    out.sort(key=lambda x: abs(x["diff"]))
    return out[:n]
