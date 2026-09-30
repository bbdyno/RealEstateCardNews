"""정적 사이트 빌드: data/realestate.db → dist/

  .venv/bin/python -m web.build                 # 전체
  .venv/bin/python -m web.build --only 서울      # 일부 지역만(개발용)

한 주소 = 한 페이지(단지·동·지역·예산대마다). 검색에 잡히게 하려는 구조다. 페이지는 시군구 단위로 만들어
메모리를 적게 쓴다.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import re
import shutil
import time
from html import unescape
from collections import defaultdict
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from analytics import core
from collector import db
from . import charts, fmt

HERE = Path(__file__).parent
ROOT = db.ROOT
NAV = [("/", "홈", "home"), ("/budget/", "예산별", "wallet"), ("/highs/", "신고가", "fire"), ("/rank/", "랭킹", "rank"),
       ("/offi/", "오피스텔", "offi"), ("/villa/", "빌라", "villa"), ("/redevelop/", "재개발", "crane")]
TABS = [("/", "홈", "home"), ("/budget/", "예산별", "wallet"), ("/highs/", "신고가", "fire"),
        ("/villa/", "빌라·오피", "offi"), ("/redevelop/", "재개발", "crane")]
STAGES = ["구역지정", "추진위", "조합설립", "사업시행", "관리처분", "이주·철거", "착공", "준공"]
KIND_LABEL = {"apt": "아파트", "offi": "오피스텔", "rh": "빌라", "sh": "단독·다가구"}
# 3D 아이콘: Microsoft Fluent Emoji(MIT 라이선스, 출처는 바닥글). jsDelivr 가 GitHub 저장소 파일을 그대로 내준다.
_FLUENT = "https://cdn.jsdelivr.net/gh/microsoft/fluentui-emoji@main/assets/{0}/3D/{1}_3d.png"
I3D = {k: _FLUENT.format(n.replace(" ", "%20"), n.lower().replace(" ", "_")) for k, n in {
    "home": "House", "house": "House", "city": "Cityscape", "offi": "Office building", "building": "Office building",
    "villa": "Houses", "crane": "Building construction", "trend": "Chart increasing", "down": "Chart decreasing",
    "wallet": "Money bag", "coin": "Coin", "rank": "Trophy", "fire": "Fire", "key": "Key", "percent": "Key",
    "warn": "Warning", "gap": "Money with wings", "pin": "Round pushpin", "search": "Magnifying glass tilted left",
    "compare": "Balance scale", "bars": "Bar chart", "chart": "Bar chart", "elevator": "Elevator",
    "calendar": "Spiral calendar", "grid": "Classical building", "receipt": "Receipt", "bulb": "Light bulb"}.items()}


def load_sponsors(today: dt.date, f: Path | None = None) -> list[dict]:
    """sponsors.yaml 에서 오늘 게재 중인 직접 광고만."""
    f = f or ROOT / "sponsors.yaml"
    items = (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("sponsors") or [] if f.exists() else []
    out = []
    for sp in items:
        start, end = (dt.date.fromisoformat(str(sp[k])) if sp.get(k) else None for k in ("start", "end"))
        if (start and today < start) or (end and today > end) or not (sp.get("url") and sp.get("title")):
            continue
        out.append({**sp, "regions": [str(r) for r in sp.get("regions") or []]})
    return out


def load_cfg() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


class Site:
    def __init__(self, out: Path, today: dt.date, cfg: dict, demo: bool, asof: str, has_redevelop: bool):
        self.out, self.today, self.cfg = out, today, cfg
        self.regions = {r["code"]: r for r in db.regions()}
        self.sido = {}                       # 시도 코드(앞 두 자리) → 약칭
        for r in self.regions.values():
            self.sido.setdefault(r["code"][:2], r["sido_short"])
        self.pages: list[str] = []
        env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]),
                          trim_blocks=True, lstrip_blocks=True)
        env.filters.update(fmt.FILTERS)
        env.globals.update(
            cx_url=self.cx_url, region_name=self.region_name, age=fmt.age, bigsplit=fmt.big, charts=charts,
            sido_name=lambda code: self.sido.get(code, code), BAND_HINT=core.BAND_HINT, BANDS=core.BANDS,
            eok_label=lambda e: "1억 미만" if e == 0 else (f"{e}억 이상" if e >= cfg["build"]["budget_max_eok"] else f"{e}억대"),
            STAGES=STAGES, KIND_LABEL=KIND_LABEL, I3D=I3D, today_year=today.year, ads=cfg["ads"], site=cfg["site"], **fmt.FILTERS)
        self.env = env
        self.sponsors = load_sponsors(today)
        self.base = {"site": cfg["site"], "ads": cfg["ads"], "verify": cfg["verify"], "nav": NAV if has_redevelop else [n for n in NAV if n[0] != "/redevelop/"],
                     # 재개발 자료가 없으면 빈 페이지로 보내지 않는다 — 하단 탭 자리는 랭킹이 대신한다
                     "tabs": TABS if has_redevelop else [t if t[0] != "/redevelop/" else ("/rank/", "랭킹", "rank") for t in TABS],
                     "analytics": cfg.get("analytics") or {},
                     "demo": demo, "asof": asof, "has_redevelop": has_redevelop,
                     # 페이지 내용이 날마다 바뀌지 않게: 캐시 번호는 CSS 내용 해시, 수집일은 /meta.json 에서 채운다
                     "build_id": hashlib.sha1(b"".join((HERE / "static" / f).read_bytes()
                                                      for f in ("style.css", "app.js", "../templates/macros.html"))).hexdigest()[:8]}
        env.globals["build_id"] = self.base["build_id"]        # 가져온 매크로(icon)에서도 쓰도록

    def sponsor(self, code: str | None = None):
        """이 페이지(시군구 5자리·시도 2자리·전국 None)에 넣을 직접 광고 하나. 좁은 지역 계약을 먼저."""
        for sp in sorted(self.sponsors, key=lambda x: -max((len(r) for r in x["regions"]), default=0)):
            if not sp["regions"] or (code and any(code.startswith(r) for r in sp["regions"])):
                return sp
        return None

    # 주소
    @staticmethod
    def cx_url(cx) -> str:
        """단지 페이지 주소. 거래가 적어 페이지를 만들지 않은 단지는 시군구 페이지로 보낸다."""
        if not cx.page:
            return f"/r/{cx.sgg}/"
        return f"/{'c' if cx.kind == 'apt' else 'o'}/{cx.cid}/"

    def region_name(self, sgg: str) -> str:
        r = self.regions.get(sgg)
        return f"{r['sido_short']} {r['name']}" if r else sgg

    def render(self, tpl: str, path: str, section: str = "", **ctx) -> None:
        html = self.env.get_template(tpl).render(**self.base, path=path, section=section, **ctx)
        html = breadcrumb_ld(html, self.cfg["site"]["base_url"].rstrip("/"))
        html = SPACES.sub("\n", html)          # 들여쓰기·빈 줄 제거(페이지 용량 — Pages 1GB)
        f = self.out / path.strip("/") / "index.html" if path.endswith("/") else self.out / path.lstrip("/")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(html, encoding="utf-8")
        if path.endswith("/"):
            self.pages.append(path)


SPACES = re.compile(r"[ \t]*\n\s*")
CRUMBS = re.compile(r'<div class="crumbs">(.*?)</div>', re.S)
ANCHOR = re.compile(r'<a href="([^"]+)">(.*?)</a>', re.S)


def breadcrumb_ld(html: str, base_url: str) -> str:
    """보이는 경로 줄(전국 › 서울 › 강남구)을 읽어 검색엔진용 BreadcrumbList 구조화 데이터를 붙인다."""
    m = CRUMBS.search(html)
    if not m or "<a href" not in m.group(1):
        return html
    items = []
    for i, part in enumerate(m.group(1).split("›"), 1):
        a = ANCHOR.search(part)
        name = unescape(re.sub(r"<[^>]+>", "", a.group(2) if a else part)).strip()
        el = {"@type": "ListItem", "position": i, "name": name}
        if a:
            el["item"] = base_url + a.group(1)
        items.append(el)
    ld = json.dumps({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": items},
                    ensure_ascii=False, separators=(",", ":"))
    return html.replace(m.group(0), m.group(0) + f'<script type="application/ld+json">{ld}</script>', 1)


class Agg:
    """전국·시도 집계(월별 거래 수와 평당가 목록)."""

    def __init__(self):
        self.count = defaultdict(int)
        self.ppp = defaultdict(list)
        self.ratios = defaultdict(list)          # 같은 단지 비교 비율(core.same_complex_ratios) — 시군구 것을 모은다

    def add_ratios(self, ratios: dict) -> None:
        for m, v in ratios.items():
            self.ratios[m].extend(v)

    def add(self, rows) -> None:
        for r in rows:
            if r["kind"] == "apt" and r["trade"] == "sale" and not r["cancelled"] and r["price"] and r["area"]:
                m = r["ymd"][:7]
                self.count[m] += 1
                if not r["direct"]:
                    self.ppp[m].append(r["price"] / (r["area"] / core.PY))

    def _rwin(self, base: str, back: int) -> list[float]:
        return [v for i in range(3) for v in self.ratios.get(core.add_months(base, -back - i), [])]

    def months(self, today: dt.date, base: str, n: int = 24) -> list[tuple]:
        """월별 (월, 거래 수, 평당가, 집계중). 평당가 흐름은 같은 단지 비교로 내고 수준만 최근 3개월 중위 평당가에 맞춘다
        (거래 구성에 따른 출렁임 제거 — core.same_complex_ratios). 비교할 거래가 모자라면 원래 중위값."""
        cur = today.strftime("%Y-%m")
        now, level = self._rwin(base, 0), self.window(base)
        scale = level / core.median(now) if level and len(now) >= 3 * core.INDEX_MIN else None
        out, m = [], core.add_months(cur, -(n - 1))
        while m <= cur:
            r = self.ratios.get(m, [])
            p = core.median(r) * scale if scale and len(r) >= core.INDEX_MIN else (None if scale else core.median(self.ppp.get(m, [])))
            out.append((m, self.count.get(m, 0), p, m > base))
            m = core.add_months(m, 1)
        return out

    def window(self, base: str, back: int = 0) -> float | None:
        """최근 3개월(back 개월 전부터) 중위 평당가 — 지금 수준."""
        ms = [core.add_months(base, -back - i) for i in range(3)]
        return core.median([v for m in ms for v in self.ppp.get(m, [])])

    def change(self, base: str) -> float | None:
        """직전 3개월 대비 변화 — 같은 단지 비교(모자라면 원래 중위값)."""
        now, prev = self._rwin(base, 0), self._rwin(base, 3)
        if len(now) >= 3 * core.INDEX_MIN and len(prev) >= 3 * core.INDEX_MIN:
            return core.change(core.median(now), core.median(prev))
        return core.change(self.window(base), self.window(base, 3))


def light(cx):
    """시군구를 넘어 모아 두는 목록(예산별·신고가·전세가율·오피스텔)용 가벼운 사본. 거래 이력은 뺀다 — 담아 두면 전국 거래가
    통째로 메모리에 남는다(실데이터에서 6.6GB)."""
    return dataclasses.replace(cx, sales=[], rents=[], series=[], by_band={})


def pair(wide: str, narrow: str) -> str:
    """넓은 화면용·좁은 화면용 차트를 함께 넣고 CSS 로 하나만 보인다(폰에서 축 글자가 작아지지 않게)."""
    if not wide and not narrow:
        return ""
    return f'<div class="cw">{wide}</div><div class="cn">{narrow}</div>'


def month_charts(months: list[tuple], base: str) -> dict:
    """월별 [(월, 거래 수, 중위 평당가, 집계중)] → 막대(거래 수)·꺾은선(평당가) SVG. 폰용은 최근 12개월만 크게."""
    def draw(ms, width, label_every, height_bars=210, height_area=220):
        labels = [fmt.month(m) for m, *_ in ms]
        counts = [c for _, c, _, _ in ms]
        hl = next((i for i, (m, *_) in enumerate(ms) if m == base), len(ms) - 1)
        pending = {i for i, (*_, p) in enumerate(ms) if p}
        prev = counts[hl - 1] if hl > 0 else None
        chip = fmt.pct(counts[hl] / prev - 1) if prev else None
        ppp_vals = [p for _, _, p, _ in ms]
        ppp_plot = [None if pend else p for (_, _, p, pend) in ms]
        chip2 = fmt.eok(ppp_vals[hl]) if ppp_vals[hl] else None
        return (charts.bars(counts, labels, highlight=hl, chip=chip, pending=pending, label_every=label_every,
                            fmt=lambda v: f"{v:,.0f}", width=width, height=height_bars),
                charts.area(ppp_plot, labels, highlight=hl, chip=chip2, label_every=label_every, fmt=fmt.eok,
                            width=width, height=height_area))
    wb, wa = draw(months, 600, 3)
    nb, na = draw(months[-12:], 340, 3, 230, 230)
    _, na24 = draw(months, 340, 6, 230, 230)
    return {"bars": pair(wb, nb), "area": pair(wa, na),
            # 좁은 카드(홈 왼쪽 등)는 넓은 화면에서도 좁은 판을 쓴다
            "area_narrow": na24}


def build(out: Path, today: dt.date, only: str | None = None) -> dict:
    cfg = load_cfg()
    c = db.connect()
    c.execute("CREATE INDEX IF NOT EXISTS deals_sgg ON deals(sgg)")
    demo = db.has_demo(c)
    last = c.execute("SELECT MAX(fetched_at) m FROM deals").fetchone()["m"]
    base = core.base_month(today)
    collected = dt.datetime.fromtimestamp(last).strftime("%Y-%m-%d") if last else None
    asof = f"기준월 {fmt.month_long(base)}"
    zones_all = [dict(z) for z in c.execute("SELECT * FROM redevelop ORDER BY sgg, zone")]
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    site = Site(out, today, cfg, demo, asof, bool(zones_all))
    since_highs = (today - dt.timedelta(days=cfg["build"]["highs_days"])).isoformat()
    since_budget = core.add_months(base, -(cfg["build"]["budget_months"] - 1)) + "-01"
    thin_max = cfg["build"].get("tiers", {}).get("thin_max", 4)
    rich_min = cfg["build"].get("tiers", {}).get("rich_min", 20)

    nat, sido_agg = Agg(), defaultdict(Agg)
    summaries, highs_all, offi_all, villa_all, search = [], [], [], [], []
    budget = defaultdict(list)                  # (시도코드, 억대) → [(cx, 거래)]
    jeonse_cx = []
    zones_by_sgg = defaultdict(list)
    for z in zones_all:
        zones_by_sgg[z["sgg"]].append(z)

    regions = sorted(site.regions.values(), key=lambda r: r["code"])
    if only:
        keys = {k.strip() for k in only.split(",")}
        regions = [r for r in regions if r["code"] in keys or r["sido_short"] in keys or r["name"] in keys]
    t0 = time.time()
    n_pages = 0
    for r in regions:
        rows = [dict(x) for x in c.execute("SELECT * FROM deals WHERE sgg=?", (r["code"],))]
        if not rows:
            continue
        nat.add(rows)
        sido_agg[r["code"][:2]].add(rows)
        apts = core.build_complexes(rows, "apt")
        offis = core.build_complexes(rows, "offi")
        ratios = core.same_complex_ratios(apts)
        nat.add_ratios(ratios)
        sido_agg[r["code"][:2]].add_ratios(ratios)
        for cx in list(apts.values()) + list(offis.values()):
            # 3년 매매(해제 제외)+전월세가 기준 이하이면 단지 페이지를 만들지 않는다(가치 낮은 대량 페이지 방지, Pages 용량)
            cx.page = sum(1 for s in cx.sales if not s["cancelled"]) + len(cx.rents) > thin_max
        st = core.region_stats(rows, "apt", today, apts)
        st_o = core.region_stats(rows, "offi", today, offis)
        st_v = core.region_stats(rows, "rh", today)
        highs = core.new_highs(apts, since_highs)
        villa = core.villa_by_dong(rows, today)
        zones = zones_by_sgg.get(r["code"], [])
        live_apts = [cx for cx in apts.values() if cx.last_sale]
        by_count = sorted(live_apts, key=lambda cx: -sum(1 for s in cx.sales if s["ymd"] >= since_budget))
        by_drop = sorted((cx for cx in live_apts if cx.drop is not None), key=lambda cx: cx.drop)
        offi_list = sorted((o for o in offis.values() if o.yield_), key=lambda o: -o.yield_)
        summary = {"r": r, "st": st, "st_o": st_o, "st_v": st_v, "highs": len(highs),
                   "offi_yield": core.median(o.yield_ for o in offi_list), "n_cx": len(live_apts),
                   "spark": [p for _, _, p, pend in st.months if not pend][-12:]}
        summaries.append(summary)
        site.render("region.html", f"/r/{r['code']}/", section="", r=r, st=st, st_o=st_o, st_v=st_v,
                    ch=month_charts(st.months, st.base), highs=highs[:12], by_count=by_count[:15],
                    by_drop=by_drop[:15], by_new=sorted(live_apts, key=lambda cx: cx.last_sale["ymd"], reverse=True)[:15],
                    offi=offi_list[:8], villa=villa[:12], zones=zones, summary=summary, sponsor=site.sponsor(r["code"]),
                    sido_code=r["code"][:2])
        n_pages += 1
        dong_cx = defaultdict(list)
        for cx in live_apts:
            dong_cx[cx.umd].append(cx)
        write_compare_data(out, r["code"], list(apts.values()) + list(offis.values()), today)
        for cx in list(apts.values()) + list(offis.values()):
            if not cx.page:
                continue
            pool = list(apts.values()) if cx.kind == "apt" else list(offis.values())
            types, cdata, qs, qtable = complex_view(cx, pool, today)
            n_trades = sum(1 for x in cx.sales if not x["cancelled"]) + len(cx.rents)
            site.render("complex.html", site.cx_url(cx), section="/offi/" if cx.kind == "offi" else "", cx=cx, r=r,
                        rich=n_trades >= rich_min, sponsor=site.sponsor(cx.sgg), coupang_ctx=coupang_context(cx, today),
                        types=types, cdata=cdata, qs=qs, qtable=qtable, cancelled_highs=core.cancelled_highs(cx)[:5],
                        neighbors=[x for x in dong_cx.get(cx.umd, []) if x.cid != cx.cid][:8],
                        zones=[z for z in zones if z["umd"] == cx.umd])
            n_pages += 1
            search.append([cx.name, f"{r['sido_short']} {r['name']} {cx.umd}", site.cx_url(cx), r["code"]])
            if cx.kind == "apt" and cx.last_sale and cx.last_sale["ymd"] >= since_budget:
                eok = min(cx.last_sale["price"] // 10000, cfg["build"]["budget_max_eok"])
                budget[(r["code"][:2], eok)].append(light(cx))
            if cx.kind == "apt" and cx.jeonse_ratio:
                jeonse_cx.append(light(cx))
        for v in villa:
            site.render("villa_dong.html", f"/v/{r['code']}/{v['umd']}/", section="/villa/", r=r, v=v,
                        chart=pair(*(charts.area([q[1] for q in v["quarters"]], [q[0][2:] for q in v["quarters"]],
                                                 chip=fmt.eok(v["quarters"][-1][1]) if v["quarters"] else None,
                                                 label_every=e, fmt=fmt.eok, width=w, height=h)
                                     for w, e, h in ((600, 2, 220), (340, 3, 240)))),
                        zones=[z for z in zones if z["umd"] == v["umd"]])
            n_pages += 1
            villa_all.append({"r": r, "v": {**v, "recent": v["recent"][:6]}})
            search.append([f"{v['umd']} 빌라", f"{r['sido_short']} {r['name']}", f"/v/{r['code']}/{v['umd']}/"])
        highs_all += [{**h, "cx": light(h["cx"])} for h in highs]
        offi_all += [light(o) for o in offi_list]
        search.append([r["name"], r["sido_short"], f"/r/{r['code']}/"])
    t_regions = time.time() - t0

    # 시도·전국
    base_months = nat.months(today, base)
    by_sido = defaultdict(list)
    for s in summaries:
        by_sido[s["r"]["code"][:2]].append(s)
    sido_rows = []
    for code, agg in sorted(sido_agg.items()):
        ms = agg.months(today, base)
        now_c = agg.count.get(base, 0)
        prev_c = agg.count.get(core.add_months(base, -1), 0)
        sido_rows.append({"code": code, "name": site.sido[code], "count": now_c,
                          "count_chg": core.change(now_c, prev_c), "ppp": agg.window(base),
                          "ppp_chg": agg.change(base),
                          "spark": [p for _, _, p, pend in ms if not pend][-12:]})
        site.render("sido.html", f"/r/{code}/", sido_code=code, name=site.sido[code], sponsor=site.sponsor(code),
                    ch=month_charts(ms, base), row=sido_rows[-1],
                    regions=sorted(by_sido[code], key=lambda s: -(s["st"].count_base or 0)),
                    highs=sorted([h for h in highs_all if h["cx"].sgg[:2] == code], key=lambda h: h["deal"]["ymd"], reverse=True)[:10],
                    eoks=sorted({e for (sc, e) in budget if sc == code}))
    highs_all.sort(key=lambda h: h["deal"]["ymd"], reverse=True)
    nat_now = nat.count.get(base, 0)
    nat_prev = nat.count.get(core.add_months(base, -1), 0)
    nat_yoy = nat.count.get(core.add_months(base, -12), 0)
    home = {"count": nat_now, "count_chg": core.change(nat_now, nat_prev), "count_yoy": core.change(nat_now, nat_yoy),
            "ppp": nat.window(base), "ppp_chg": nat.change(base),
            "jeonse": core.median(s["st"].jeonse_ratio for s in summaries),
            "offi_yield": core.median(o.yield_ for o in offi_all), "highs": len(highs_all)}
    site.render("index.html", "/", section="/", home=home, ch=month_charts(base_months, base), sido_rows=sido_rows,
                highs=highs_all[:8], base=base, zones=zones_all,
                budget_hot=sorted(((sc, e, len(v)) for (sc, e), v in budget.items()), key=lambda x: -x[2])[:12],
                villa_top=sorted((x for x in villa_all if x["v"]["land_ppp"]), key=lambda x: -x["v"]["n"])[:6],
                offi_top=offi_all and sorted(offi_all, key=lambda o: -o.yield_)[:6])

    # 예산별
    for (sc, e), cxs in budget.items():
        panes = []
        for b in ["전체"] + core.BANDS:
            sel = [cx for cx in cxs if b == "전체" or core.band(cx.last_sale["area"]) == b]
            if sel:
                panes.append({"band": b, "cxs": sorted(sel, key=lambda cx: (cx.drop or 0))})
        site.render("budget.html", f"/budget/{sc}/{e}/", section="/budget/", sido_code=sc, name=site.sido[sc], eok=e,
                    max_eok=cfg["build"]["budget_max_eok"], panes=panes,
                    eoks=sorted({x for (s2, x) in budget if s2 == sc}))
    site.render("budget_index.html", "/budget/", section="/budget/",
                table=[(sc, site.sido[sc], sorted((e, len(v)) for (s2, e), v in budget.items() if s2 == sc))
                       for sc in sorted({sc for sc, _ in budget})], max_eok=cfg["build"]["budget_max_eok"])
    # 모아 보기
    site.render("highs.html", "/highs/", section="/highs/", highs=highs_all[:200], days=cfg["build"]["highs_days"],
                sidos=sorted({h["cx"].sgg[:2] for h in highs_all}))
    ranked = [s for s in summaries if s["st"].count_base]
    site.render("rank.html", "/rank/", section="/rank/", base=base,
                by_count=sorted(ranked, key=lambda s: -s["st"].count_base)[:20],
                # 거래량 증가는 작년 같은 달이 30건 이상인 곳만(몇 건짜리 군 지역이 +400% 로 위를 채우지 않게)
                by_yoy=sorted((s for s in ranked if (s["st"].count_yoy or 0) >= 30), key=lambda s: -(s["st"].count_base / s["st"].count_yoy))[:20],
                by_ppp=sorted((s for s in ranked if s["st"].median_ppp), key=lambda s: -s["st"].median_ppp)[:20],
                # 상승·하락률은 같은 단지 비교로 낸 곳만(거래 몇 건짜리 군 지역의 ±100% 가 위를 채우지 않게)
                by_up=sorted((s for s in ranked if s["st"].change_sure), key=lambda s: -s["st"].ppp_change)[:20],
                by_down=sorted((s for s in ranked if s["st"].change_sure), key=lambda s: s["st"].ppp_change)[:20],
                by_jeonse=sorted((s for s in summaries if s["st"].jeonse_ratio), key=lambda s: -s["st"].jeonse_ratio)[:20])
    site.render("jeonse.html", "/jeonse/", section="/rank/",
                regions=sorted((s for s in summaries if s["st"].jeonse_ratio), key=lambda s: -s["st"].jeonse_ratio),
                cxs=sorted(jeonse_cx, key=lambda cx: -cx.jeonse_ratio)[:60],
                villa_high=[(x["r"], x["v"]["umd"], h) for x in villa_all for h in x["v"]["high_ratio"]][:40])
    site.render("offi.html", "/offi/", section="/offi/", offi=sorted(offi_all, key=lambda o: -o.yield_)[:60],
                regions=sorted((s for s in summaries if s["offi_yield"]), key=lambda s: -s["offi_yield"]))
    site.render("villa_index.html", "/villa/", section="/villa/",
                groups=_group_villa(villa_all), top=sorted((x for x in villa_all if x["v"]["land_ppp"]),
                                                           key=lambda x: -x["v"]["land_ppp"])[:15])
    zones_sorted = sorted(zones_all, key=lambda z: (z["sido"], z["sgg_name"], -(z["stage_no"] or 0)))
    if zones_all:
        site.render("redevelop_index.html", "/redevelop/", section="/redevelop/", zones=zones_sorted,
                    sidos=sorted({z["sido"] for z in zones_all}), bizs=sorted({z["biz"] for z in zones_all if z["biz"]}))
    villa_key = {(x["r"]["code"], x["v"]["umd"]): x["v"] for x in villa_all}
    for z in zones_all:
        site.render("redevelop_zone.html", f"/redevelop/{z['id']}/", section="/redevelop/", z=z,
                    villa=villa_key.get((z["sgg"], z["umd"])), r=site.regions.get(z["sgg"]))
        search.append([z["zone"], f"{z['sgg_name']} 재개발", f"/redevelop/{z['id']}/"])
    site.render("compare.html", "/compare/", section="")
    for slug in ("about", "methodology", "privacy", "terms", "ads"):
        site.render(f"page_{slug}.html", f"/{slug}/", base=base)
    site.render("404.html", "/404.html")

    # 정적 파일 · 검색 색인 · 사이트맵
    shutil.copytree(HERE / "static", out / "static")
    for f in sorted((HERE / "root").glob("*")):          # 검색엔진 소유 확인 파일 등(사이트 맨 위)
        if f.suffix in (".html", ".txt"):
            shutil.copy2(f, out / f.name)
    write_icon_sprite(site.env, out / "static" / "icons.svg")
    (out / "search.json").write_text(json.dumps(search, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / "meta.json").write_text(json.dumps({"collected": collected, "base_month": base}), encoding="utf-8")
    base_url = cfg["site"]["base_url"].rstrip("/")
    write_sitemaps(out, base_url, site.pages)
    # 캐시 규칙(Netlify·Cloudflare Pages 공통 _headers 형식). CSS 는 ?v=내용해시 라 오래 캐시한다.
    # 겹치는 규칙은 두 곳 모두 값을 이어 붙이므로 전체(/*) 규칙은 두지 않는다 — HTML 기본값(매번 확인)이면 된다.
    (out / "_headers").write_text("/static/*\n  Cache-Control: public, max-age=31536000, immutable\n", encoding="utf-8")
    robots = "User-agent: *\nDisallow: /\n" if demo else f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n"
    (out / "robots.txt").write_text(robots, encoding="utf-8")
    client = cfg["ads"]["adsense"]["client"]
    if client:
        (out / "ads.txt").write_text(f"google.com, {client.replace('ca-', '')}, DIRECT, f08c47fec0942fa0\n", encoding="utf-8")
    return {"pages": len(site.pages), "regions_with_data": len(summaries), "seconds_regions": round(t_regions, 1),
            "complex_pages": n_pages, "demo": demo}


ICONS = ["home", "wallet", "trend", "building", "crane", "search", "arrow", "bars", "percent", "calendar", "house", "coin", "grid"]


def write_icon_sprite(env, path: Path) -> None:
    """선 아이콘을 <symbol> 로 모은 스프라이트. 페이지에는 <use href> 만 넣어 페이지마다 같은 경로를 되풀이하지 않는다."""
    mod = env.get_template("macros.html").make_module({"build_id": ""})
    syms = "".join(f'<symbol id="i-{n}" viewBox="0 0 24 24">{mod.icon_paths(n)}</symbol>' for n in ICONS)
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg">{syms}</svg>', encoding="utf-8")


def coupang_context(cx, today: dt.date) -> str:
    """쿠팡 블록 맥락: 5년차 이내 새 단지 → 가전·살림, 전월세가 매매의 두 배 넘게 많은 단지 → 이사, 그 밖 → 책."""
    if cx.build_year and today.year - cx.build_year + 1 <= 5:
        return "appliance"
    if len(cx.rents) > 2 * sum(1 for x in cx.sales if not x["cancelled"]):
        return "move"
    return "book"


MAX_TYPES = 4            # 단지 페이지 평형 탭 수(거래 많은 순). 나머지 평형은 평형별 요약 표에만 나온다
PT_CLS = {"lo": 0, "mid": 1, "hi": 2, "x": 3, "dir": 4, "out": 5}


def complex_view(cx, pool, today: dt.date):
    """단지 페이지 v2: 평형(면적 타입)별 요약과, 브라우저가 그릴 그래프 데이터(JSON).
    그래프를 SVG 로 굽지 않고 숫자만 넣어 페이지를 가볍게 한다(GitHub Pages 1GB)."""
    cur = today.strftime("%Y-%m")
    months = [core.add_months(cur, -i) for i in range(35, -1, -1)]
    idx = {m: i for i, m in enumerate(months)}
    types, data = [], []
    for k in core.type_keys(cx)[:MAX_TYPES]:
        ins = core.type_insight(cx, k, today)
        if not ins:
            continue
        top = ins["top_floor"]
        pts, by_m = [], defaultdict(list)
        for x in cx.sales:
            if core.area_key(x["area"]) != k or not x["price"]:
                continue
            c = ("x" if x["cancelled"] else "dir" if x["direct"] else "out" if x.get("outlier")
                 else core.floor_level(x["floor"], top))
            ym = x["ymd"][:7]
            if ym in idx:
                pts.append([idx[ym], int(x["ymd"][8:]), x["price"], PT_CLS[c], x["floor"] or 0])
            if c in ("lo", "mid", "hi"):
                by_m[ym].append(x["price"])
        fv = [f["median"] for f in ins["floors"]]
        for f in ins["floors"]:          # 차이가 보이게: 가장 싼 층 40% ~ 가장 비싼 층 100%
            f["w"] = 40 + 60 * (f["median"] - min(fv)) / (max(fv) - min(fv)) if max(fv) > min(fv) else 70
        ins["recent"] = core.recent_flagged(cx, k)
        ins["sim"] = core.similar(cx, pool, ins["area"], ins["now"], n=6 if not types else 4)
        types.append(ins)
        data.append({"k": k, "med": [round(core.median(by_m[m])) if by_m.get(m) else 0 for m in months],
                     "cnt": [len(by_m.get(m, [])) for m in months], "pts": pts,
                     "gap": [[q, round(sale), round(jeonse) if jeonse else 0] for q, _, sale, jeonse in ins["gap_q"][-8:] if sale]})
    qs, table = core.quarter_table(cx, today)
    cdata = json.dumps({"m0": months[0], "t": data}, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return types, cdata, qs, table


def complex_chart(sales, jeonse, today: dt.date) -> str:
    """단지 한 평형대: 월별 중위 매매가(실선) + 전세 중위(점선), 최근 36개월(폰은 24개월)."""
    cur = today.strftime("%Y-%m")
    by_s, by_j = defaultdict(list), defaultdict(list)
    for s in sales:
        by_s[s["ymd"][:7]].append(s["price"])
    for x in jeonse:
        by_j[x["ymd"][:7]].append(x["deposit"])

    def draw(n, width, every, height):
        months = [core.add_months(cur, -i) for i in range(n - 1, -1, -1)]
        sv = [core.median(by_s.get(m, [])) for m in months]
        jv = [core.median(by_j.get(m, [])) for m in months]
        last = next((v for v in reversed(sv) if v), None)
        hl = max((i for i, v in enumerate(sv) if v), default=None)
        return charts.area(sv, [fmt.month(m) for m in months], highlight=hl, chip=fmt.eok(last) if last else None,
                           second=jv, label_every=every, fmt=fmt.eok, width=width, height=height)
    return pair(draw(36, 600, 6, 220), draw(24, 340, 6, 240))


def write_compare_data(out: Path, sgg: str, cxs, today: dt.date) -> None:
    """단지 비교 도구용 시군구 파일 dist/data/<시군구>.json. 단지마다 주력 평형의 월별 중위 매매가(24개월)와 요약값."""
    cur = today.strftime("%Y-%m")
    months = [core.add_months(cur, -i) for i in range(23, -1, -1)]
    data = {}
    for cx in cxs:
        live = core.priced(cx.sales)
        if not live:
            continue
        main = max(core.BANDS, key=lambda b: sum(1 for x in live if core.band(x["area"]) == b))
        by_m = defaultdict(list)
        for x in live:
            if core.band(x["area"]) == main:
                by_m[x["ymd"][:7]].append(x["price"])
        ls = cx.last_sale
        data[cx.cid] = {"n": cx.name, "k": cx.kind, "u": cx.umd, "y": cx.build_year, "b": main,
                        "p": ls["price"], "a": ls["area"], "d": ls["ymd"], "pk": cx.peak["price"] if cx.peak else None,
                        "dr": round(cx.drop, 4) if cx.drop is not None else None,
                        "j": round(cx.jeonse_ratio, 4) if cx.jeonse_ratio else None,
                        "yl": round(cx.yield_, 4) if cx.yield_ else None,
                        "s": [core.median(by_m.get(m, [])) for m in months]}
    f = out / "data" / f"{sgg}.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"months": months, "cx": data}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def write_sitemaps(out: Path, base_url: str, pages: list[str], chunk: int = 40000) -> None:
    """사이트맵 한 파일은 주소 5만 개까지다. 넘으면 나눠 쓰고 sitemap.xml 을 목록(index)으로 만든다."""
    ns = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
    parts = [pages[i:i + chunk] for i in range(0, len(pages), chunk)] or [[]]
    body = lambda ps: "".join(f"<url><loc>{base_url}{p}</loc></url>" for p in ps)
    if len(parts) == 1:
        (out / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset {ns}>{body(parts[0])}</urlset>', encoding="utf-8")
        return
    for i, ps in enumerate(parts, 1):
        (out / f"sitemap-{i}.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset {ns}>{body(ps)}</urlset>', encoding="utf-8")
    idx = "".join(f"<sitemap><loc>{base_url}/sitemap-{i}.xml</loc></sitemap>" for i in range(1, len(parts) + 1))
    (out / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><sitemapindex {ns}>{idx}</sitemapindex>', encoding="utf-8")


def _group_villa(items):
    g = defaultdict(list)
    for x in items:
        g[(x["r"]["sido_short"], x["r"]["name"], x["r"]["code"])].append(x["v"])
    return sorted(g.items())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(ROOT / "dist"))
    p.add_argument("--only")
    p.add_argument("--today", help="YYYY-MM-DD (기본: 오늘)")
    a = p.parse_args()
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    t = time.time()
    info = build(Path(a.out), today, a.only)
    print(json.dumps({**info, "total_seconds": round(time.time() - t, 1)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
