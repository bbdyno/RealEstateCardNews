"""오늘의 카드뉴스 한 묶음을 만들어 자동 검수 → 인스타 게시 → 텔레그램 알림.

  .venv/bin/python -m cards.post                         # 예산표(점심) — 만들고 검수하고 올린다
  .venv/bin/python -m cards.post --series cash           # 현금으로 어디까지(저녁)
  .venv/bin/python -m cards.post --series cash --dry-run # 만들고 검수까지만(올리지 않음, 알림은 보낸다)

시리즈마다 후보를 날짜로 돌려 가며 고르고, 단지가 10곳 미만이거나 최근에 같은 제목을 올렸으면 다음 후보로 넘어간다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import traceback

from . import budget, cash, check, loan, publish

# (시도, 억대 범위, 평형대) — 수도권 위주. 지방 광역시 시리즈는 다음 단계에서 붙인다
SERIES = [("서울", range(6, 21), ("30평대", "20평대")),
          ("경기", range(4, 13), ("30평대", "20평대")),
          ("인천", range(3, 9), ("30평대", "20평대"))]
SLUG = {"서울": "seoul", "경기": "gyeonggi", "인천": "incheon"}
MAX_TRIES = 12
RECENT = 14          # 같은 제목을 다시 올리지 않는 범위(최근 게시물 수)
TAGS = "#아파트실거래가 #실거래가 #내집마련 #부동산 #아파트시세 #집값 #집값레이더"


def rotate(items: list, today: dt.date) -> list:
    """날짜마다 시작점이 바뀌는 순서 — 매일 다른 후보가 먼저 나온다."""
    k = today.toordinal() * 7 % len(items)
    return items[k:] + items[:k]


def candidates(today: dt.date) -> list[tuple[str, int, str]]:
    return rotate([(s, e, b) for s, es, bs in SERIES for b in bs for e in es], today)


def posted(title: str, recent: list[str]) -> bool:
    return any((r or "").strip().startswith(title) for r in recent[:RECENT])


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


def make_budget(today: dt.date, recent: list[str], tried: list[str]):
    for sido, eok, band in candidates(today)[:MAX_TRIES]:
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
        bad = check.check_rows(rows, eok, base, today) + check.check_images(files, meta["overflow"])
        return title, files, cap, bad, f"budget-{SLUG.get(sido, 'region')}-{eok}-{band[:2]}"
    return None


# ── 현금으로 어디까지 ────────────────────────────────────────────────────────

def cash_candidates(today: dt.date) -> list[tuple[str, str]]:
    return rotate([(k, s) for k in cash.PERSONAS for s in ("서울", "경기", "인천")], today)


def cash_caption(key: str, sido: str, meta: dict, today: dt.date) -> str:
    p, m, pl = cash.PERSONAS[key], meta["main"], meta["plans"]
    eok = cash.eok
    stop = {"DSR": "소득(DSR)", "LTV": f"LTV {int(m.ltv * 100)}%", "한도": "주담대 6억 한도"}[m.binding]
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
        f"✔ {loan.RULES_AS_OF}(LTV·주담대 한도·스트레스 DSR 3%)",
        "✔ 금리 4%·30년·기존 대출 없음 가정 — 실제 한도는 은행에서 꼭 확인하세요",
        f"✔ 국토부 실거래({today.month}월 {today.day}일 신고분까지) · 해제·직거래 제외",
        "",
        "👉 우리 단지 층별 가격·모든 거래는 프로필 링크(jipgapradar.kr)",
        "저장해 두고 내 조건과 비교해 보세요. 궁금한 조건은 댓글로 남겨 주세요!",
        "",
        f"#{sido}아파트 #{p['label'].replace(' ', '')} #생애최초 #주택담보대출 #DSR #LTV #부동산대책 {TAGS}",
    ]
    return "\n".join(lines)


def make_cash(today: dt.date, recent: list[str], tried: list[str]):
    for key, sido in cash_candidates(today)[:MAX_TRIES]:
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
            + [f"[비규제 계산] {b}" for b in check.check_plan(p["cash"], pl[False])]
        return title, files, cap, bad, f"cash-{key}-{SLUG.get(sido, 'region')}"
    return None


MAKERS = {"budget": make_budget, "cash": make_cash}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", choices=sorted(MAKERS), default="budget")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--repeat", action="store_true", help="최근에 올린 제목도 다시 올린다(수정판 재게시)")
    a = ap.parse_args()
    today = dt.date.today()
    live = not a.dry_run and bool(os.environ.get("IG_ACCESS_TOKEN") and os.environ.get("IG_USER_ID"))
    try:
        recent = publish.recent_captions() if live else []
        if live and today.weekday() == 0 and a.series == "budget":   # 월요일마다 토큰 유효기간을 늘리고 남은 날을 확인
            days = publish.refresh_token()
            if days is not None and days < 20:
                publish.notify(f"⚠️ 집값레이더 인스타 토큰이 {days:.0f}일 남았습니다. Meta 개발자 화면에서 다시 발급해 주세요.")
        tried: list[str] = []
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
        publish.notify(f"✅ 집값레이더 인스타 게시 완료\n{title} · {len(files)}장 · 검수 통과\n{link}", files[0])
        return 0
    except Exception as e:  # noqa: BLE001 — 실패는 반드시 알린다
        traceback.print_exc()
        publish.notify(f"❌ 집값레이더 카드 게시 오류({a.series})\n{type(e).__name__}: {str(e)[:500]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
