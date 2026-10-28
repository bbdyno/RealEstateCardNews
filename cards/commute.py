"""업무지구 출퇴근 릴스의 데이터 — 업무지구 권역 안에서 예산·평형에 맞는 단지를 실거래로 뽑는다.

  .venv/bin/python -m cards.commute                       → 오늘 데이터로 편 목록(후보 수) 출력
  .venv/bin/python -m cards.commute 여의도 8~9억 59형      → 그 편의 TOP 5

업무지구 정의(권역 동·노선·대략 시간)는 config.yaml 의 commute.hubs. 뽑기 규칙:
최근 6개월 아파트 매매, 해제·직거래·이상 거래 제외(core.priced), 공공임대 단지 제외, 같은 단지·평형 3건 이상,
3년 매매 10건 이상(사이트에 단지 페이지가 있는 곳). 금액은 6개월 중앙값. 순위는 6개월 거래가 많은 순 — '추천 순위'가 아니다.

편 세 가지: 예산(업무지구 × 예산 × 평형) · 신축(2010년 이후 준공, 중앙값이 낮은 순) · 맞벌이(두 업무지구 권역이 겹치는 동).
"""
from __future__ import annotations

import datetime as dt
import re
import statistics
import sys
from dataclasses import dataclass
from functools import lru_cache

import yaml

from analytics import core
from collector import db

from .budget import MIN_DEALS, short_name

MONTHS_DAYS = 183
MIN_SAME = 3             # 같은 단지·평형 6개월 거래 수
TOP_N = 5
NEW_FROM = 2010
SIZES = {"59형": (55, 62), "84형": (76, 86)}
# (이름, 하한, 상한) 만원 — 중앙값이 [하한, 상한)
BANDS = [("4억대", 40000, 50000), ("5~6억", 50000, 60000), ("6~7억", 60000, 70000), ("7~8억", 70000, 80000),
         ("8~9억", 80000, 90000), ("9~10억", 90000, 100000), ("10~12억", 100000, 120000), ("12~15억", 120000, 150000)]
NEW_MAX = 150000         # 신축 편도 15억 미만만(그 위는 이 시리즈 시청자 예산 밖)
EXCLUDE = re.compile(r"임대|행복주택|국민주택")
# 서울 지하철 노선 색(공식 색 기준)
LINE_COLOR = {"1": "#0052A4", "2": "#00A84D", "3": "#EF7C1C", "4": "#00A5DE", "5": "#996CAC", "6": "#CD7C2F",
              "7": "#747F00", "8": "#E6186C", "9": "#BDB092", "신분당": "#D4003B", "수인분당": "#F5A200",
              "경의중앙": "#77C4A3", "경춘": "#0C8E72", "공항": "#0090D2", "경강": "#0054A6", "김포골드": "#A17800", "신림": "#6789CA"}


@dataclass(frozen=True)
class Episode:
    kind: str                 # budget · new · dual
    hub: str
    band: str = ""
    size: str = ""
    hub2: str = ""

    @property
    def key(self) -> str:
        return "|".join(x for x in (self.kind, self.hub, self.hub2, self.band, self.size) if x)

    @property
    def title(self) -> str:
        """캡션 첫 줄의 앞부분 — 게시 기록에서 이 편이 나왔는지 찾는 열쇠."""
        if self.kind == "budget":
            return f"{self.hub} 출근 {self.band} {self.size}"
        if self.kind == "new":
            return f"{self.hub} 출근 신축 {self.size}"
        return f"맞벌이 {self.hub}+{self.hub2} {self.size}"


def hubs() -> list[dict]:
    return yaml.safe_load((db.ROOT / "config.yaml").read_text(encoding="utf-8"))["commute"]["hubs"]


def hub(name: str) -> dict:
    return next(h for h in hubs() if h["name"] == name)


def line_label(lines: list) -> str:
    """['5', '7', '신림'] → '5·7호선·신림선'."""
    nums = [str(x) for x in lines if str(x).isdigit()]
    named = [f"{x}선" if x not in ("공항",) else "공항철도" for x in map(str, lines) if not x.isdigit()]
    return "·".join(([("·".join(nums) + "호선")] if nums else []) + named)


def josa(word: str, with_batchim: str, without: str) -> str:
    """받침이 있으면 앞, 없으면 뒤('가산' → '이라면', '여의도' → '라면')."""
    c = ord(word[-1]) - 0xAC00
    return with_batchim if 0 <= c < 11172 and c % 28 else without


def minutes_label(m: list) -> str:
    return f"약 {m[0]}~{m[1]}분"


def band_of(price: float) -> str | None:
    return next((b for b, lo, hi in BANDS if lo <= price < hi), None)


def size_of(area: float) -> str | None:
    return next((s for s, (lo, hi) in SIZES.items() if lo <= area <= hi), None)


@lru_cache(maxsize=64)
def _complexes(sgg: str) -> tuple:
    rows = [dict(x) for x in db.connect().execute("SELECT * FROM deals WHERE sgg=? AND kind='apt' AND trade='sale'", (sgg,))]
    return tuple(core.build_complexes(rows, "apt").values())


@lru_cache(maxsize=1)
def _gu_names() -> dict:
    return {r["code"]: r["name"] for r in db.regions()}


def candidates_from(cxs, area: dict, gu: str, today: dt.date) -> list[dict]:
    """한 권역 묶음의 단지·평형 후보(DB 없이도 시험할 수 있게 단지 목록을 받는다)."""
    since = (today - dt.timedelta(days=MONTHS_DAYS)).isoformat()
    umds = set(area.get("umd") or [])
    out = []
    for cx in cxs:
        if umds and cx.umd not in umds or EXCLUDE.search(cx.name or ""):
            continue
        if sum(1 for s in cx.sales if not s["cancelled"]) < MIN_DEALS:
            continue
        by_size: dict[str, list] = {}
        for s in core.priced(cx.sales):
            sz = size_of(s["area"])
            if sz and s["ymd"] >= since:
                by_size.setdefault(sz, []).append(s)
        for sz, ds in by_size.items():
            if len(ds) < MIN_SAME:
                continue
            ds.sort(key=lambda s: s["ymd"])
            prices = [s["price"] for s in ds]
            areas = sorted(round(s["area"]) for s in ds)
            out.append({"sgg": cx.sgg, "gu": gu.split()[-1], "umd": cx.umd, "name": short_name(cx.name), "cid": cx.cid,
                        "built": cx.build_year, "size": sz, "area": areas[len(areas) // 2], "n": len(ds),
                        "median": int(statistics.median(prices)), "lo": min(prices), "hi": max(prices),
                        "last_ymd": ds[-1]["ymd"], "last_price": ds[-1]["price"],
                        "lines": [str(x) for x in area["lines"]], "line": line_label(area["lines"]), "min": list(area["min"]),
                        "href": f"/c/{cx.cid}/"})
    return out


def hub_candidates(name: str, today: dt.date) -> list[dict]:
    """업무지구 권역 전체 후보. 같은 단지가 두 권역 묶음에 걸리면 가까운 쪽 하나만."""
    h, best = hub(name), {}
    for area in h["areas"]:
        for x in candidates_from(_complexes(area["sgg"]), area, _gu_names().get(area["sgg"], ""), today):
            x["to"] = h["to"]
            k = (x["cid"], x["size"])
            if k not in best or x["min"] < best[k]["min"]:
                best[k] = x
    return list(best.values())


def _dedupe_names(rows: list[dict]) -> list[dict]:
    """같은 구·같은 이름(단지 번호가 갈라진 경우)은 거래 많은 쪽 하나만."""
    best: dict = {}
    for x in rows:
        k = (x["gu"], x["name"], x["size"])
        if k not in best or x["n"] > best[k]["n"]:
            best[k] = x
    return list(best.values())


def select(ep: Episode, today: dt.date) -> tuple[list[dict], list[dict]]:
    """(TOP 5, 조건에 맞는 후보 전체). 순위 1이 맨 앞."""
    if ep.kind == "dual":
        a = {(x["cid"], x["size"]): x for x in hub_candidates(ep.hub, today) if x["size"] == ep.size}
        b = {(x["cid"], x["size"]): x for x in hub_candidates(ep.hub2, today) if x["size"] == ep.size}
        pool = []
        for k in a.keys() & b.keys():
            x = dict(a[k])
            x["to2"], x["line2"], x["lines2"], x["min2"] = b[k]["to"], b[k]["line"], b[k]["lines"], b[k]["min"]
            pool.append(x)
        pool = _dedupe_names(pool)
        pool.sort(key=lambda x: (-x["n"], x["median"]))
    else:
        pool = [x for x in hub_candidates(ep.hub, today) if x["size"] == ep.size]
        if ep.kind == "budget":
            pool = [x for x in pool if band_of(x["median"]) == ep.band]
            pool = _dedupe_names(pool)
            pool.sort(key=lambda x: (-x["n"], _neg(x["last_ymd"])))
        else:
            pool = [x for x in pool if (x["built"] or 0) >= NEW_FROM and x["median"] < NEW_MAX]
            pool = _dedupe_names(pool)
            pool.sort(key=lambda x: (x["median"], -x["n"]))
    top = pool[:TOP_N]
    for i, x in enumerate(top, 1):
        x["rank"] = i
    return top, pool


def _neg(ymd: str) -> str:
    """최근 계약일이 앞으로 오게 정렬하는 열쇠(문자열 날짜를 뒤집는다)."""
    return "".join(chr(0x10FFFF - ord(c)) for c in ymd)


def highlights(rows: list[dict]) -> dict:
    """마무리 장면의 세 줄: 가장 가까운 곳 · 가장 새 아파트 · 중앙값이 가장 낮은 곳."""
    near = min(rows, key=lambda x: (sum(x["min"]) + sum(x.get("min2") or [0, 0]), -x["n"]))
    new = max(rows, key=lambda x: (x["built"] or 0, x["n"]))
    low = min(rows, key=lambda x: x["median"])
    return {"near": near, "new": new, "low": low}


# ── 편 목록 ──────────────────────────────────────────────────────────────────

DUALS = [("여의도", "강남"), ("여의도", "구디·가산"), ("판교", "강남"), ("광화문", "여의도"), ("마곡", "여의도"),
         ("성수", "강남"), ("잠실", "강남"), ("용산", "여의도"), ("상암", "광화문"), ("성수", "잠실")]


def all_episodes() -> list[Episode]:
    """업무지구가 연달아 나오지 않게 섞은 전체 편. 예산 편 사이사이에 신축·맞벌이 편이 끼어든다."""
    names = [h["name"] for h in hubs()]
    budget = [Episode("budget", n, b, s) for b, _, _ in BANDS for s in SIZES for n in names]
    special = [Episode("new", n, size=s) for s in SIZES for n in names] + \
              [Episode("dual", a, size=s, hub2=b) for s in SIZES for a, b in DUALS]
    out, k = [], 0
    for i, ep in enumerate(budget):
        out.append(ep)
        if i % 4 == 3 and k < len(special):
            out.append(special[k])
            k += 1
    return out + special[k:]


def order(log: list[dict], eps: list[Episode] | None = None) -> list[Episode]:
    """한 번도 안 나온 편이 먼저(목록 순), 그다음 마지막으로 나온 때가 오래된 순 — 한 바퀴 다 돌아야 같은 편이 다시 나온다."""
    eps = eps if eps is not None else all_episodes()
    last: dict[str, tuple[str, int]] = {}
    for i, e in enumerate(log):
        t = e.get("title") or ""
        for ep in eps:
            if t == ep.title:
                last[ep.key] = (e.get("at") or e.get("date") or "", i)
    return sorted(eps, key=lambda ep: (ep.key in last, last.get(ep.key, ("", 0)), eps.index(ep)))


def main() -> int:
    today = dt.date.today()
    if len(sys.argv) >= 4:
        rows, pool = select(Episode("budget", sys.argv[1], sys.argv[2], sys.argv[3]), today)
        print(f"후보 {len(pool)}곳")
        for x in rows:
            print(x["rank"], x["gu"], x["umd"], x["name"], x["built"], x["size"], x["n"], x["median"], x["line"], minutes_label(x["min"]))
        return 0
    ok = 0
    for ep in all_episodes():
        rows, pool = select(ep, today)
        n = len(pool)
        ok += n >= TOP_N
        print(f"{'○' if n >= TOP_N else '×'} {ep.title}: {n}곳")
    print(f"만들 수 있는 편 {ok}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
