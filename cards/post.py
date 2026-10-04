"""오늘의 카드뉴스 한 묶음을 만들어 자동 검수 → 인스타 게시 → 텔레그램 알림.

  .venv/bin/python -m cards.post                         # 예산표(점심) — 만들고 검수하고 올린다
  .venv/bin/python -m cards.post --series cash           # 현금으로 어디까지(저녁)
  .venv/bin/python -m cards.post --series cash --dry-run # 만들고 검수까지만(올리지 않음, 알림은 보낸다)

시리즈마다 후보를 날짜로 돌려 가며 고르고, 단지가 10곳 미만이거나 최근에 같은 제목을 올렸으면 다음 후보로 넘어간다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import itertools
import re
import os
import sys
import traceback

from . import budget, cash, check, loan, publish, rank

# (시도, 억대 범위, 평형대) — 수도권 위주. 지방 광역시 시리즈는 다음 단계에서 붙인다
SERIES = [("서울", range(6, 21), ("30평대", "20평대")),
          ("경기", range(4, 13), ("30평대", "20평대")),
          ("인천", range(3, 9), ("30평대", "20평대"))]
# 관심이 몰리는 가격대 — 후보에 한 번 더 넣어 더 자주 나오게
HOT = [("서울", range(7, 13), ("30평대", "20평대")),
       ("경기", range(5, 9), ("30평대", "20평대")),
       ("인천", range(4, 7), ("30평대", "20평대"))]
SLUG = {"서울": "seoul", "경기": "gyeonggi", "인천": "incheon", "부산": "busan", "대구": "daegu", "대전": "daejeon",
        "전남광주": "gwangju", "울산": "ulsan", "세종": "sejong"}
MAX_TRIES = 12
RECENT = 14          # 같은 제목을 다시 올리지 않는 범위(최근 게시물 수)
TAGS = "#아파트실거래가 #실거래가 #내집마련 #부동산 #아파트시세 #집값 #집값레이더"


def rotate(items: list, today: dt.date) -> list:
    """날짜마다 시작점이 바뀌는 순서 — 매일 다른 후보가 먼저 나온다."""
    k = today.toordinal() * 7 % len(items)
    return items[k:] + items[:k]


def _interleave(series) -> list[tuple[str, int, str]]:
    per = [[(s, e, b) for b in bs for e in es] for s, es, bs in series]
    return [x for grp in itertools.zip_longest(*per) for x in grp if x]


def candidates(today: dt.date) -> list[tuple[str, int, str]]:
    """서울·경기·인천을 번갈아 — 한 시도에 몰리지 않게. 관심 가격대는 두 번 들어간다."""
    return rotate(_interleave(SERIES) + _interleave(HOT), today)


def posted(title: str, recent: list[str]) -> bool:
    return any((r or "").strip().startswith(title) for r in recent[:RECENT])


def korean(files: list, cap: str, rows: list[dict]) -> list[str]:
    """카드 글자(렌더 때 남긴 text.txt)와 캡션에 영어가 섞이지 않았는지."""
    names = [x.get(k) for x in rows for k in ("name", "gu", "umd")]
    card = (files[0].parent / "text.txt").read_text(encoding="utf-8") if files else ""
    return check.check_korean([("카드", card), ("캡션", cap)], names)


def won(v: float) -> str:
    """만원 → '8천만 원', '1억 2천만 원'."""
    e, r = divmod(int(v), 10000)
    parts = ([f"{e}억"] if e else []) + ([f"{r // 1000}천만"] if r >= 1000 else [])
    return " ".join(parts) + " 원"


# ── 예산 × 평형 실거래 표 ──────────────────────────────────────────────────

def caption(sido: str, eok: int, band: str, meta: dict, today: dt.date) -> str:
    c = meta["ctx"]
    band_label = band.replace("평대", "평형")
    gu = " · ".join(f"{g} {n}" for g, n in c["top_gu"])
    drops = [x for x in meta["near_hi"] if x["vs_hi"] is not None and x["vs_hi"] < -0.0005][:2]
    lines = [
        f"{sido} {eok}억대 {band_label}, 최근 3개월 실제로 계약된 단지 {c['n']}곳 🏠"
        + (f"\n(표에는 거래가 많은 {c['n_shown']}곳)" if c.get("n_shown", c["n"]) < c["n"] else ""),
        f"그중 {c['highs']}곳({round(c['highs'] / c['n'] * 100)}%)은 3년 최고가를 새로 썼어요.",
        "",
        f"📍 거래가 많은 시·구: {gu}",
    ]
    if drops:
        lines.append("📉 최고가보다 많이 내린 단지: " + ", ".join(f"{x['gu']} {x['name']}({x['vs_hi'] * 100:.1f}%)" for x in drops))
    lines += [
        "",
        f"✔ 호가 아닌 국토부 실거래({today.month}월 {today.day}일 신고분까지)",
        "✔ 해제·직거래 거래 제외 ✔ 3년 거래 10건 넘는 단지만",
        "",
        "👉 단지별 층별 가격·갭·모든 거래 그래프는 프로필 링크(jipgapradar.kr)",
        "저장해 두고 예산별로 비교해 보세요.",
        "",
        f"#{sido}아파트 #{eok}억대아파트 #{band.replace('대', '')}대 #신고가 {TAGS}",
    ]
    return "\n".join(lines)


def make_budget(today: dt.date, recent: list[str], tried: list[str], only: tuple | None = None, band_only: str | None = None):
    cands = [only] if only else [c for c in candidates(today) if not band_only or c[2] == band_only][:MAX_TRIES]
    for sido, eok, band in cands:
        title = f"{sido} {eok}억대 {band.replace('평대', '평형')}"
        if posted(title, recent):
            tried.append(f"{title}(최근에 올림)")
            continue
        rows, base = budget.pick(sido, eok, band, today)
        if len(rows) < 10:
            tried.append(f"{title}({len(rows)}곳)")
            continue
        files, meta = budget.render(sido, eok, band, today, rows_base=(rows, base))
        cap = caption(sido, eok, band, meta, today)
        bad = check.check_rows(rows, eok, base, today) + check.check_images(files, meta["overflow"]) + korean(files, cap, rows)
        return title, files, cap, bad, f"budget-{SLUG.get(sido, 'region')}-{eok}-{band[:2]}"
    return None


# ── 현금으로 어디까지 ────────────────────────────────────────────────────────

def cash_candidates(today: dt.date) -> list[tuple[str, str]]:
    return rotate([(k, s) for k in cash.PERSONAS for s in ("서울", "경기", "인천")], today)


def cash_caption(key: str, sido: str, meta: dict, today: dt.date) -> str:
    p, m, pl = cash.PERSONAS[key], meta["main"], meta["plans"]
    eok = cash.eok
    stop = {"DSR": "소득 한도", "LTV": f"집값의 {int(m.ltv * 100)}% 한도", "한도": "주담대 6억 한도"}[m.binding]
    alt = loan.max_price(p["cash"], p["income"], True, not p["first"])
    lines = [
        f"현금 {eok(p['cash'])} {p['label']} · {sido} 아파트는 최대 {eok(m.price)}까지 🏠",
        f"연소득 {won(p['income'])}, {'생애최초' if p['first'] else '생애최초 아님'} 기준이에요.",
        "",
        f"💸 대출은 {stop}에서 막혀 {eok(m.loan)}. 매달 약 {cash.man(loan.monthly(m.loan))}원씩 30년 갚아요.",
    ]
    if meta["mixed"]:
        lines.append(f"📍 경기 규제지역 12곳은 {eok(pl[True].price)}, 그 외 지역은 {eok(pl[False].price)}까지.")
    elif sido != "인천" and abs(alt.price - m.price) >= 1000:
        lines.append(f"📍 {'생애최초가 아니면' if p['first'] else '생애최초라면'} {'규제지역 12곳은 ' if sido == '경기' else ''}{eok(alt.price)}까지예요.")
    if meta["mode_py"]:
        lines.append(f"🏢 이 값에 최근 3개월 실제로 계약된 단지 {meta['n']}곳 — 많이 산 집은 {meta['mode_py']}평대, 평균 {meta['avg_age']}년 된 아파트.")
    lines += [
        "📌 거래 많은 곳: " + " · ".join(f"{g} {n}" for g, n in meta["top_gu"]),
        "",
        f"✔ {loan.RULES_AS_OF}(집값 대비 대출 비율·주담대 한도·소득 심사 때 금리 3%p 가산)",
        "✔ 금리 4%·30년·기존 대출 없음 가정 — 실제 한도는 은행에서 꼭 확인하세요",
        f"✔ 국토부 실거래({today.month}월 {today.day}일 신고분까지) · 해제·직거래 제외",
        "",
        "👉 우리 단지 층별 가격·모든 거래는 프로필 링크(jipgapradar.kr)",
        "저장해 두고 내 조건과 비교해 보세요. 궁금한 조건은 댓글로 남겨 주세요!",
        "",
        f"#{sido}아파트 #{p['label'].replace(' ', '')} #생애최초 #주택담보대출 #대출한도 #부동산대책 {TAGS}",
    ]
    return "\n".join(lines)


def make_cash(today: dt.date, recent: list[str], tried: list[str], only: tuple | None = None):
    for key, sido in ([only] if only else cash_candidates(today)[:MAX_TRIES]):
        p = cash.PERSONAS[key]
        title = f"현금 {cash.eok(p['cash'])} {p['label']} · {sido}"
        if posted(title, recent):
            tried.append(f"{title}(최근에 올림)")
            continue
        picked = cash.pick(key, sido, today)
        if len(picked[0]) < 10:
            tried.append(f"{title}({len(picked[0])}곳)")
            continue
        files, meta = cash.render(key, sido, today, picked=picked)
        cap = cash_caption(key, sido, meta, today)
        rows, base, pl = picked
        bad = check.check_rows(rows, None, base, today, bounds=lambda x: (x["top"] * cash.LOW - 1, x["top"] + 1)) \
            + check.check_images(files, meta["overflow"]) \
            + [f"[규제지역 계산] {b}" for b in check.check_plan(p["cash"], pl[True])] \
            + [f"[비규제 계산] {b}" for b in check.check_plan(p["cash"], pl[False])] + korean(files, cap, rows)
        return title, files, cap, bad, f"cash-{key}-{SLUG.get(sido, 'region')}"
    return None


# ── 랭킹(아침) ───────────────────────────────────────────────────────────────

WEEKDAY_FMT = ["highs", "drops", "hot", "cancels", "gu", "highs", "drops"]      # 월~일
RANK_SIDOS = ["서울", "경기", "부산", "서울", "인천", "경기", "대구", "서울", "대전", "경기", "전남광주", "울산", "세종"]
RANK_CAP = {
    "highs":   ("🔥", "이전 최고보다 {up}", "✔ 같은 단지·같은 평형 3년 최고가를 넘은 계약만 · 40% 넘게 뛴 건 입력 오류일 수 있어 제외", "#신고가 #아파트신고가"),
    "drops":   ("📉", "3년 최고가보다 {up}", "✔ 같은 평형 거래 3건 이상 · 최고가 한 건만 튄 단지는 제외", "#아파트하락 #급매"),
    "cancels": ("⚠️", "직전 최고보다 {up} 높게 계약했다가 취소", "✔ 최근 6개월 계약 중 해제 신고된 것 — 실제로 팔린 값이 아니에요", "#신고가해제 #집값띄우기"),
    "hot":     ("🏆", "최근 3개월 {n3}건", "✔ 해제·직거래 제외 · 전용 40㎡ 이상", "#거래량 #인기아파트"),
    "gu":      ("📊", "직전 3개월보다 {up}", "✔ 같은 단지끼리 비교해 '비싼 단지가 많이 팔린 달' 착시를 뺐어요", "#집값순위 #아파트시세"),
}


def rank_caption(fmt: str, sido: str, rows: list[dict], today: dt.date) -> str:
    f = rank.FORMATS[fmt]
    emoji, lead, note, tags = RANK_CAP[fmt]
    pct = lambda v: f"{v * 100:+.1f}%".replace("-", "−")
    lines = [f"{sido} {f['head']} {emoji}", f"{f['sub']}", ""]
    for x in rows[:3]:
        what = lead.format(up=pct(x["up"]) if x.get("up") is not None else "", n3=x.get("n3"))
        if fmt == "gu":
            lines.append(f"{x['rank']}위 {x['gu']} — {what}")
        else:
            lines.append(f"{x['rank']}위 {x['gu']} {x['name']} {x['py']}평 {x['price'] / 10000:g}억 — {what}")
    if fmt == "gu" and len(rows) > 3:
        x = rows[-1]
        lines.append(f"가장 약한 곳: {x['gu']} {pct(x['up'])}")
    lines += [
        "",
        note,
        f"✔ 국토부 실거래({today.month}월 {today.day}일 신고분까지)",
        "",
        "👉 우리 단지 층별 가격·모든 거래는 프로필 링크(jipgapradar.kr)",
        "저장해 두고 우리 동네가 있는지 확인해 보세요. 다른 지역이 궁금하면 댓글로!",
        "",
        f"#{sido}아파트 {tags} {TAGS}",
    ]
    return "\n".join(lines)


def second_fmt(today: dt.date) -> str:
    """오후 랭킹: 아침과 다른 형식."""
    order = ["highs", "hot", "drops", "gu", "cancels"]
    first = WEEKDAY_FMT[today.weekday()]
    k = (today.toordinal() + 2) % len(order)
    return order[k] if order[k] != first else order[(k + 1) % len(order)]


def make_rank(today: dt.date, recent: list[str], tried: list[str], fmt: str | None = None, sido_only: str | None = None,
              offset: int = 0):
    fmt = fmt or WEEKDAY_FMT[today.weekday()]
    f = rank.FORMATS[fmt]
    seen = []
    for sido in ([sido_only] if sido_only else rotate(RANK_SIDOS, today + dt.timedelta(days=offset))):
        if sido in seen:
            continue
        seen.append(sido)
        if len(seen) > 6:
            break
        title = f"{sido} {f['head']}"
        if posted(title, recent):
            tried.append(f"{title}(최근에 올림)")
            continue
        rows = rank.pick(fmt, sido, today)
        if len(rows) < 10:
            tried.append(f"{title}({len(rows)}줄)")
            continue
        files, meta = rank.render(fmt, sido, today, rows)
        cap = rank_caption(fmt, sido, rows, today)
        bad = check.check_rank(rows, fmt) + check.check_images(files, meta["overflow"]) + korean(files, cap, rows)
        return title, files, cap, bad, f"rank-{fmt}-{SLUG.get(sido, 'region')}"
    return None


def make_budget_pair(today: dt.date, recent: list[str], tried: list[str]):
    """밤 예산표: 점심에 올린 같은 시도·억대의 20평형(아파트썸처럼 20평대·30평대를 짝으로). 없으면 20평대 후보에서."""
    for e in reversed(publish.posted_log()):
        if e.get("date") == today.isoformat() and e.get("series") == "budget":
            m = re.match(r"(\S+) (\d+)억대 30평형", e.get("title", ""))
            if m:
                made = make_budget(today, recent, tried, only=(m[1], int(m[2]), "20평대"))
                if made:
                    return made
            break
    return make_budget(today, recent, tried, band_only="20평대")


# 하루 다섯 번: 08:10 rank · 12:10 budget(30평형) · 15:40 rank2 · 19:40 cash · 21:40 budget2(같은 억대 20평형)
MAKERS = {"rank": make_rank, "cash": make_cash,
          "budget": lambda t, r, tr: make_budget(t, r, tr, band_only="30평대"),
          "rank2": lambda t, r, tr: make_rank(t, r, tr, fmt=second_fmt(t), offset=4),
          "budget2": make_budget_pair}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", choices=sorted(MAKERS), default="budget")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--repeat", action="store_true", help="최근에 올린 제목도 다시 올린다(수정판 재게시)")
    ap.add_argument("--fmt", choices=sorted(rank.FORMATS), help="랭킹 형식을 직접 고른다(수동 추가 게시)")
    ap.add_argument("--sido", help="랭킹·예산표 시도를 직접 고른다")
    ap.add_argument("--eok", type=int, help="예산표 억대를 직접 고른다(--sido 와 함께)")
    ap.add_argument("--band", default="30평대", help="예산표 평형대(30평대·20평대)")
    ap.add_argument("--persona", choices=sorted(cash.PERSONAS), help="현금 카드 가구 유형(--sido 와 함께)")
    a = ap.parse_args()
    today = dt.date.today()
    live = not a.dry_run and bool(os.environ.get("IG_ACCESS_TOKEN") and os.environ.get("IG_USER_ID"))
    try:
        recent = publish.recent_captions() if live else []
        if live and today.weekday() == 0 and a.series == "budget":   # 월요일마다 토큰 유효기간을 늘리고 남은 날을 확인
            days = publish.refresh_token()
            if days is not None and days < 20:
                publish.notify(f"⚠️ 집값레이더 인스타 토큰이 {days:.0f}일 남았습니다. Meta 개발자 화면에서 다시 발급해 주세요.")
        manual = bool(a.fmt or a.sido or a.eok or a.persona)
        if live and not a.repeat and not manual:        # 맥 예약과 GitHub 예약이 둘 다 돌아도 하루 한 번만
            if any(e.get("date") == today.isoformat() and e.get("series") == a.series for e in publish.posted_log()):
                print(f"오늘 {a.series} 은 이미 올렸습니다 — 건너뜀")
                return 0
        tried: list[str] = []
        if a.series.startswith("rank") and manual:
            made = make_rank(today, [] if a.repeat else recent, tried, a.fmt, a.sido)
        elif a.series == "cash" and a.persona and a.sido:
            made = make_cash(today, [] if a.repeat else recent, tried, only=(a.persona, a.sido))
        elif a.series.startswith("budget") and a.eok and a.sido:
            made = make_budget(today, [] if a.repeat else recent, tried, only=(a.sido, a.eok, a.band))
        else:
            made = MAKERS[a.series](today, [] if a.repeat else recent, tried)
        if not made:
            publish.notify("ℹ️ 집값레이더: 오늘 올릴 만한 후보가 없어 건너뜁니다\n" + ", ".join(tried))
            return 0
        title, files, cap, bad, slug = made
        bad += check.check_caption(cap, [] if a.repeat else recent)
        if bad:
            print("검수 실패:", *bad, sep="\n- ")
            publish.notify(f"🚫 집값레이더 카드 검수 실패 — 올리지 않았습니다\n{title}\n- " + "\n- ".join(bad[:15]), files[0])
            return 1
        if not live:
            publish.notify(f"🧪 [시험] 집값레이더 카드 검수 통과(게시 안 함)\n{title} · {len(files)}장\n\n{cap[:600]}", files[0])
            print(cap)
            return 0
        urls = publish.upload(files, slug)
        media_id = publish.publish(urls, cap)
        link = publish.permalink(media_id) or ""
        try:
            publish.add_log({"date": today.isoformat(), "series": a.series + ("-manual" if manual else ""), "title": title, "id": media_id, "link": link,
                             "at": dt.datetime.now().isoformat(timespec="minutes")})
        except Exception as e:  # noqa: BLE001 — 기록 실패로 게시 알림을 막지 않는다
            print("게시 기록 실패:", e)
        publish.notify(f"✅ 집값레이더 인스타 게시 완료\n{title} · {len(files)}장 · 검수 통과\n{link}", files[0])
        return 0
    except Exception as e:  # noqa: BLE001 — 실패는 반드시 알린다
        traceback.print_exc()
        publish.notify(f"❌ 집값레이더 카드 게시 오류({a.series})\n{type(e).__name__}: {str(e)[:500]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
