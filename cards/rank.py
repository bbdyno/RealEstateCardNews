"""랭킹 카드 — 신고가 순위 · 많이 내린 단지 · 신고가 찍고 해제 · 거래 많은 단지 · 시·구 집값 변화 순위.

  .venv/bin/python -m cards.rank highs 서울     → out/cards/rank-highs-서울/01.jpg …

형식마다 행을 만드는 함수(rows_*)와 표 열 정의(COLS)만 다르고, 표지·표·마무리 카드는 같은 틀을 쓴다.
아침 슬롯에서 요일마다 형식을 바꾸고, 시도를 돌려 가며 올린다(수도권만이 아니라 광역시까지).
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

from .budget import MIN_DEALS, OUT, ROWS, env, shoot, short_name, sido_complexes

MAX_TABLES = 2            # 랭킹은 20위·40위까지(표 1~2장)
MIN_AREA = 40             # 전용 40㎡ 미만(원룸형 소형)은 빼고 — 몇천만 원짜리가 1위에 오르면 정보가 안 된다
TOP = ROWS * MAX_TABLES

# 형식별 표지 색·아이콘·문구. head 는 표지 큰 제목(시도 뒤), what 은 1위 카드의 값 이름
FORMATS = {
    "highs":   dict(head="신고가 순위", sub="최근 한 달 계약 · 같은 평형 3년 최고가 경신", icon="fire", period="최근 한 달 계약", bg="#FFE1EC", ac="#F04452",
                    what="이전 최고보다", unit="pct_up"),
    "drops":   dict(head="하락 순위", sub="최근 3개월 실거래 · 3년 최고가보다 많이 내린 단지", icon="down", period="최근 3개월 실거래", bg="#E3EEFF", ac="#3182F6",
                    what="3년 최고가보다", unit="pct_down"),
    "cancels": dict(head="해제된 신고가", sub="최근 6개월 · 신고가로 계약했다가 취소(집값 띄우기 의심 신호)", icon="warn", period="최근 6개월 계약", bg="#FFF4CC", ac="#E08A00",
                    what="직전 최고보다", unit="pct_up"),
    "hot":     dict(head="거래량 순위", sub="최근 3개월 매매 건수 · 해제·직거래 제외", icon="rank", period="최근 3개월", bg="#EFFBD0", ac="#4C8A00",
                    what="최근 3개월", unit="count"),
    "gu":      dict(head="시·구 집값 순위", sub="같은 단지끼리 비교 · 최근 3개월 vs 그 전 3개월", icon="trend", period="같은 단지끼리 비교", bg="#ECE6FF", ac="#6B4EE6",
                    what="직전 3개월보다", unit="pct_signed"),
}
# 표 열: (머리말, 키, 폭px(None=남는 폭), 형식)
_BASE = [("#", "rank", 54, "rank"), ("시·구", "gu", 112, "gu"), ("단지", "name", None, "name"), ("평", "py", 52, "int")]
COLS = {
    "highs":   _BASE + [("신고가", "price", 122, "eok_b"), ("이전 최고", "prev", 104, "eok_m"), ("오른 폭", "up", 136, "pct_up"), ("계약일", "ymd", 100, "md")],
    "drops":   _BASE + [("실거래", "price", 122, "eok_b"), ("3년 최고", "prev", 104, "eok_m"), ("내린 폭", "up", 136, "pct_down"), ("계약일", "ymd", 100, "md")],
    "cancels": _BASE + [("해제된 값", "price", 122, "eok_b"), ("직전 최고", "prev", 104, "eok_m"), ("차이", "up", 136, "pct_up"), ("계약일", "ymd", 100, "md")],
    "hot":     [("#", "rank", 54, "rank"), ("시·구", "gu", 112, "gu"), ("단지", "name", None, "name"), ("연차", "age", 60, "int"),
                ("거래", "n3", 80, "cnt"), ("주력 평", "py", 80, "int"), ("최근가", "price", 122, "eok_b"), ("최고 대비", "up", 140, "pct_signed")],
    "gu":      [("#", "rank", 54, "rank"), ("시·구", "gu_one", None, "name"), ("3개월 변화", "up", 146, "pct_signed"), ("", "bar", 190, "bar"),
                ("평당가", "ppp", 124, "man"), ("거래", "n3", 116, "cnt")],
}
SIDOS = ["서울", "경기", "인천", "부산", "대구", "대전", "전남광주", "울산", "세종"]


def _since(today: dt.date, days: int) -> str:
    return (today - dt.timedelta(days=days)).isoformat()


def _row(gu, cx, deal, prev, up, today, **kw) -> dict:
    if " " not in gu and gu.endswith("시") and gu.startswith("세종"):   # 세종은 구가 없어 동 이름을 쓴다
        gu = cx.umd
    return dict(gu=gu, name=short_name(cx.name), umd=cx.umd, py=round(deal["area"] * 1.33 / core.PY),
                age=(today.year - cx.build_year + 1) if cx.build_year else None,
                price=deal["price"], prev=prev, up=up, ymd=deal["ymd"], **kw)


def _n3y(cx) -> int:
    return sum(1 for s in cx.sales if not s["cancelled"])


def rows_highs(sido: str, today: dt.date) -> list[dict]:
    since = _since(today, 35)
    out = []
    for gu, cx in sido_complexes(sido):
        if _n3y(cx) < MIN_DEALS:
            continue
        for h in core.new_highs({cx.cid: cx}, since):
            if 0.005 <= h["up"] <= 0.4 and h["deal"]["area"] >= MIN_AREA:                         # 40% 넘게 뛴 건 입력 오류일 가능성이 커 뺀다
                out.append(_row(gu, cx, h["deal"], h["prev"], h["up"], today))
    best: dict = {}
    for x in out:                                               # 한 단지는 가장 많이 오른 거래 하나만
        k = (x["gu"], x["name"])
        if k not in best or x["up"] > best[k]["up"]:
            best[k] = x
    return sorted(best.values(), key=lambda x: -x["up"])[:TOP]


def rows_drops(sido: str, today: dt.date) -> list[dict]:
    since = _since(today, 92)
    out = []
    for gu, cx in sido_complexes(sido):
        if _n3y(cx) < MIN_DEALS:
            continue
        live = core.priced(cx.sales)
        for k in {core.area_key(s["area"]) for s in live}:
            same = [s for s in live if core.area_key(s["area"]) == k]
            last = same[0]
            if last["ymd"] < since or len(same) < 3 or last["area"] < MIN_AREA:
                continue
            tops = sorted((s["price"] for s in same), reverse=True)
            if tops[1] < tops[0] * 0.9:                         # 최고가 한 건만 튀었으면(다음 최고와 10% 넘게 차이) 비교 기준으로 안 쓴다
                continue
            prior = [s["price"] for s in same[1:] if s["ymd"] >= _since(dt.date.fromisoformat(last["ymd"]), 183)]
            if len(prior) >= 2 and last["price"] < core.median(prior) * 0.8:    # 직전 6개월 시세보다 20% 넘게 싼 한 건은 특수 거래로 본다
                continue
            hi = max(same, key=lambda s: s["price"])
            d = core.change(last["price"], hi["price"])
            if d is not None and -0.45 <= d <= -0.05:
                out.append(_row(gu, cx, last, hi["price"], d, today))
    best: dict = {}
    for x in out:
        k = (x["gu"], x["name"])
        if k not in best or x["up"] < best[k]["up"]:
            best[k] = x
    return sorted(best.values(), key=lambda x: x["up"])[:TOP]


def rows_cancels(sido: str, today: dt.date) -> list[dict]:
    since = _since(today, 183)                                  # 해제는 드물어 6개월을 본다
    out = []
    for gu, cx in sido_complexes(sido):
        if _n3y(cx) < MIN_DEALS:
            continue
        for h in core.cancelled_highs(cx):
            if h["deal"]["ymd"] >= since and 0.005 <= h["up"] <= 0.5 and h["deal"]["area"] >= MIN_AREA:
                out.append(_row(gu, cx, h["deal"], h["prev"], h["up"], today))
    best: dict = {}
    for x in out:
        k = (x["gu"], x["name"])
        if k not in best or x["up"] > best[k]["up"]:
            best[k] = x
    return sorted(best.values(), key=lambda x: -x["up"])[:TOP]


def rows_hot(sido: str, today: dt.date) -> list[dict]:
    since = _since(today, 92)
    out = []
    for gu, cx in sido_complexes(sido):
        live = [s for s in core.priced(cx.sales) if s["area"] >= MIN_AREA]
        recent = [s for s in live if s["ymd"] >= since]
        if len(recent) < 5:
            continue
        keys = defaultdict(int)
        for s in recent:
            keys[core.area_key(s["area"])] += 1
        k = max(keys, key=keys.get)                              # 가장 많이 팔린 평형
        same = [s for s in live if core.area_key(s["area"]) == k]
        last = same[0]
        hi = max(same, key=lambda s: s["price"])
        out.append(_row(gu, cx, last, hi["price"], core.change(last["price"], hi["price"]), today, n3=len(recent)))
    best: dict = {}
    for x in out:
        kk = (x["gu"], x["name"])
        if kk not in best or x["n3"] > best[kk]["n3"]:
            best[kk] = x
    return sorted(best.values(), key=lambda x: (-x["n3"], -x["price"]))[:TOP]


def rows_gu(sido: str, today: dt.date) -> list[dict]:
    c = db.connect()
    out = []
    for r in db.regions():
        if r["sido_short"] != sido:
            continue
        rows = [dict(x) for x in c.execute("SELECT * FROM deals WHERE sgg=? AND kind='apt' AND trade='sale'", (r["code"],))]
        if not rows:
            continue
        st = core.region_stats(rows, "apt", today, core.build_complexes(rows, "apt"))
        if not st.change_sure or st.ppp_change is None:
            continue
        n3 = sum(n for m, n, _, _ in st.months if m <= st.base and m >= core.add_months(st.base, -2))
        out.append(dict(gu=r["name"], gu_one=r["name"], name=r["name"], up=st.ppp_change, ppp=st.median_ppp, n3=n3))
    out.sort(key=lambda x: -x["up"])
    mx = max((abs(x["up"]) for x in out), default=0) or 1
    for x in out:
        x["bar"] = x["up"] / mx
    return out[:TOP]


ROWS_FN = {"highs": rows_highs, "drops": rows_drops, "cancels": rows_cancels, "hot": rows_hot, "gu": rows_gu}


def pick(fmt: str, sido: str, today: dt.date) -> list[dict]:
    rows = ROWS_FN[fmt](sido, today)
    for i, x in enumerate(rows, 1):
        x["rank"] = i
    return rows


def render(fmt: str, sido: str, today: dt.date | None = None, rows: list[dict] | None = None) -> tuple[list[Path], dict]:
    today = today or dt.date.today()
    rows = rows if rows is not None else pick(fmt, sido, today)
    f = FORMATS[fmt]
    pages = [rows[i:i + ROWS] for i in range(0, len(rows), ROWS)]
    by_gu = defaultdict(int)
    for x in rows:
        by_gu[x["gu"]] += 1
    ctx = dict(fmt=fmt, f=f, sido=sido, rows=rows, n=len(rows), pages=pages, cols=COLS[fmt], today=today, I3D=I3D,
               total=len(pages) + 2, logo=(db.ROOT / "web" / "static" / "logo.svg").as_uri(),
               top_gu=sorted(by_gu.items(), key=lambda kv: -kv[1])[:3],
               title=f"{sido} {f['head']}", chips=[f["period"], f"{today.month}.{today.day} 신고분까지"])
    out = OUT / f"rank-{fmt}-{sido}"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shots = [("rank_cover", {}), *[("rank_table", {"page": p, "no": i + 2}) for i, p in enumerate(pages)], ("budget_outro", {})]
    files, overflow = shoot(env(), shots, ctx, out)
    print(f"{fmt} {sido} {len(rows)}줄 · {len(files)}장 → {out}")
    return files, {"rows": rows, "overflow": overflow, "top_gu": ctx["top_gu"]}


if __name__ == "__main__":
    fmt, sido = (sys.argv[1:] + ["highs", "서울"][len(sys.argv[1:]):])[:2]
    render(fmt, sido)
