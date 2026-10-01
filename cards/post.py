"""오늘의 카드뉴스 한 묶음을 만들어 자동 검수 → 인스타 게시 → 텔레그램 알림.

  .venv/bin/python -m cards.post              # 만들고 검수하고 올린다
  .venv/bin/python -m cards.post --dry-run    # 만들고 검수까지만(올리지 않음, 알림은 보낸다)

지금은 '예산 × 평형대 실거래 표' 시리즈만 돈다(아파트썸 간판 형식의 실거래판). 후보를 날짜로 돌려 가며 고르고,
단지가 10곳 미만이거나 최근에 같은 제목을 올렸으면 다음 후보로 넘어간다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import traceback

from . import budget, check, publish

# (시도, 억대 범위, 평형대) — 수도권 위주. 지방 광역시 시리즈는 다음 단계에서 붙인다
SERIES = [("서울", range(6, 21), ("30평대", "20평대")),
          ("경기", range(4, 13), ("30평대", "20평대")),
          ("인천", range(3, 9), ("30평대", "20평대"))]
MAX_TRIES = 12


def candidates(today: dt.date) -> list[tuple[str, int, str]]:
    """날짜마다 시작점이 바뀌는 후보 순서 — 매일 다른 지역·억대·평형이 먼저 나온다."""
    allc = [(s, e, b) for s, es, bs in SERIES for b in bs for e in es]
    k = today.toordinal() * 7 % len(allc)
    return allc[k:] + allc[:k]


def caption(sido: str, eok: int, band: str, meta: dict) -> str:
    c, rows = meta["ctx"], meta["rows"]
    band_label = band.replace("평대", "평형")
    gu = " · ".join(f"{g} {n}" for g, n in c["top_gu"])
    drops = [x for x in meta["near_hi"] if x["vs_hi"] is not None and x["vs_hi"] < -0.0005][:2]
    lines = [
        f"{sido} {eok}억대 {band_label}, 최근 3개월 실제로 계약된 단지 {c['n']}곳 🏠"
        + (f"\n(표에는 거래가 많은 {c['n_shown']}곳)" if c.get("n_shown", c["n"]) < c["n"] else ""),
        f"그중 {c['highs']}곳({round(c['highs'] / c['n'] * 100)}%)은 3년 최고가를 새로 썼어요.",
        "",
        f"📍 거래가 많은 구: {gu}",
    ]
    if drops:
        lines.append("📉 최고가보다 많이 내린 단지: " + ", ".join(f"{x['gu']} {x['name']}({x['vs_hi'] * 100:.1f}%)" for x in drops))
    lines += [
        "",
        f"✔ 호가 아닌 국토부 실거래({meta['base'][:4]}년 {int(meta['base'][5:7])}월 기준)",
        "✔ 해제·직거래 거래 제외 ✔ 3년 거래 10건 넘는 단지만",
        "",
        "👉 단지별 층별 가격·갭·모든 거래 그래프는 프로필 링크(jipgapradar.kr)",
        "저장해 두고 예산별로 비교해 보세요.",
        "",
        f"#{sido}아파트 #{eok}억대아파트 #{band.replace('대', '')}대 #아파트실거래가 #실거래가 #신고가 #내집마련 #부동산 #아파트시세 #집값 #집값레이더",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    today = dt.date.today()
    live = not a.dry_run and bool(os.environ.get("IG_ACCESS_TOKEN") and os.environ.get("IG_USER_ID"))
    try:
        recent = publish.recent_captions() if live else []
        if live and today.weekday() == 0:                     # 월요일마다 토큰 유효기간을 늘리고 남은 날을 확인
            days = publish.refresh_token()
            if days is not None and days < 20:
                publish.notify(f"⚠️ 집값레이더 인스타 토큰이 {days:.0f}일 남았습니다. Meta 개발자 화면에서 다시 발급해 주세요.")
        tried = []
        for sido, eok, band in candidates(today)[:MAX_TRIES]:
            rows, base = budget.pick(sido, eok, band, today)
            title = f"{sido} {eok}억대 {band}"
            if len(rows) < 10:
                tried.append(f"{title}({len(rows)}곳)")
                continue
            cap = caption(sido, eok, band, {"ctx": {"n": len(rows), "n_shown": len(rows), "highs": sum(x["is_high"] for x in rows),
                                                    "top_gu": [], "band": band}, "rows": rows, "base": base, "near_hi": []})
            if any((r or "").strip().splitlines()[:1] == [cap.splitlines()[0]] for r in recent):
                tried.append(f"{title}(최근에 올림)")
                continue
            files, meta = budget.render(sido, eok, band, today, rows_base=(rows, base))
            cap = caption(sido, eok, band, meta)
            bad = check.check_rows(rows, eok, base, today) + check.check_images(files, meta["overflow"]) + \
                check.check_caption(cap, recent)
            if bad:
                publish.notify(f"🚫 집값레이더 카드 검수 실패 — 올리지 않았습니다\n{title}\n- " + "\n- ".join(bad[:15]), files[0])
                return 1
            if not live:
                publish.notify(f"🧪 [시험] 집값레이더 카드 검수 통과(게시 안 함)\n{title} · {len(files)}장\n\n{cap[:600]}", files[0])
                print(cap)
                return 0
            urls = publish.upload(files, f"budget-{sido}-{eok}-{band}")
            media_id = publish.publish(urls, cap)
            link = publish.permalink(media_id) or ""
            publish.notify(f"✅ 집값레이더 인스타 게시 완료\n{title} · {len(files)}장 · 검수 통과\n{link}", files[0])
            return 0
        publish.notify("ℹ️ 집값레이더: 오늘 올릴 만한 예산표 후보가 없어 건너뜁니다\n" + ", ".join(tried))
        return 0
    except Exception as e:  # noqa: BLE001 — 실패는 반드시 알린다
        traceback.print_exc()
        publish.notify(f"❌ 집값레이더 카드 게시 오류\n{type(e).__name__}: {str(e)[:500]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
