"""게시 전 자동 검수. 하나라도 걸리면 올리지 않고 텔레그램으로 이유를 알린다.

숫자: 표의 모든 가격이 제목의 억대 안인지, 계약일이 최근 3개월인지, 최고 대비가 말이 되는지(−60%~0%),
      같은 단지가 두 번 나오지 않는지, 기준월이 오늘 기준월과 같은지.
그림: 장수 2~10, 크기 1080×1440, JPEG, 8MB 이하, 글자가 칸을 넘치지 않는지(렌더 때 표시한 값).
캡션: 2,200자·해시태그 30개 이하, 최근 게시물과 첫 줄이 겹치지 않는지.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import re

from PIL import Image

from analytics import core


def check_rows(rows: list[dict], eok: int | None, base: str, today: dt.date, bounds=None) -> list[str]:
    """bounds(row) -> (하한, 상한) 만원. 없으면 eok 억대."""
    bounds = bounds or (lambda x: (eok * 10000, (eok + 1) * 10000 - 1))
    bad = []
    if len(rows) < 10:
        bad.append(f"단지가 {len(rows)}곳뿐(10곳 미만)")
    if base != core.base_month(today):
        bad.append(f"기준월 {base} ≠ 오늘 기준월 {core.base_month(today)}")
    since = core.add_months(base, -2) + "-01"
    seen = set()
    for x in rows:
        lo, hi = bounds(x)
        if not (lo <= x["price"] <= hi):
            bad.append(f"{x['name']} 가격 {x['price']} 이 범위({lo:.0f}~{hi:.0f}) 밖")
        if x["ymd"] < since:
            bad.append(f"{x['name']} 계약일 {x['ymd']} 이 최근 3개월 밖")
        if x["vs_hi"] is not None and not (-0.6 <= x["vs_hi"] <= 0.0001):
            bad.append(f"{x['name']} 최고 대비 {x['vs_hi']:.1%} 이상")
        if x["hi"] < x["price"]:
            bad.append(f"{x['name']} 3년 최고 {x['hi']} < 실거래 {x['price']}")
        key = (x["gu"], x["name"])
        if key in seen:
            bad.append(f"{x['name']} 중복")
        seen.add(key)
    return bad


def check_images(paths: list[Path], overflow: dict[str, int]) -> list[str]:
    bad = []
    if not 2 <= len(paths) <= 10:
        bad.append(f"장수 {len(paths)}(2~10장이어야 함)")
    for p in paths:
        with Image.open(p) as im:
            if im.size != (1080, 1440):
                bad.append(f"{p.name} 크기 {im.size}")
            if im.format != "JPEG":
                bad.append(f"{p.name} 형식 {im.format}")
        if p.stat().st_size > 8 * 1024 * 1024:
            bad.append(f"{p.name} 8MB 초과")
    bad += [f"{name} 글자 넘침 {n}칸" for name, n in overflow.items() if n]
    return bad


def check_caption(caption: str, recent: list[str]) -> list[str]:
    bad = []
    if len(caption) > 2200:
        bad.append(f"캡션 {len(caption)}자(2,200자 넘음)")
    if caption.count("#") > 30:
        bad.append("해시태그 30개 넘음")
    head = caption.strip().splitlines()[0]
    if any((r or "").strip().splitlines()[:1] == [head] for r in recent):
        bad.append("최근 게시물과 첫 줄이 같음(중복 게시)")
    return bad


def check_plan(cash: float, plan, cap: float = 60000) -> list[str]:
    """현금 카드의 계산이 맞는지: 현금 + 대출 − 비용 = 최대 집값, 대출은 LTV·한도 이하."""
    bad = []
    if abs(cash + plan.loan - plan.costs - plan.price) > 50:
        bad.append(f"계산 불일치: 현금 {cash} + 대출 {plan.loan:.0f} − 비용 {plan.costs:.0f} ≠ {plan.price:.0f}")
    if plan.loan > cap + 1 or plan.loan > plan.by_ltv + 1 or plan.loan > plan.by_dsr + 1:
        bad.append(f"대출 {plan.loan:.0f} 이 한도를 넘음")
    if not cash < plan.price < cash * 6:
        bad.append(f"최대 집값 {plan.price:.0f} 이 이상함")
    return bad


RANK_RANGE = {"highs": (0.0001, 0.5), "cancels": (0.0001, 0.5), "drops": (-0.45, -0.0001), "hot": (-0.9, 0.5), "gu": (-0.3, 0.3)}


def check_rank(rows: list[dict], fmt: str) -> list[str]:
    bad = []
    if len(rows) < 10:
        bad.append(f"{len(rows)}줄뿐(10줄 미만)")
    lo, hi = RANK_RANGE[fmt]
    seen = set()
    for x in rows:
        if x.get("up") is not None and not (lo <= x["up"] <= hi):
            bad.append(f"{x['name']} 값 {x['up']:.1%} 이 범위 밖")
        if fmt != "gu" and not x.get("price"):
            bad.append(f"{x['name']} 가격 없음")
        k = (x["gu"], x["name"])
        if k in seen:
            bad.append(f"{x['name']} 중복")
        seen.add(k)
    if [x["rank"] for x in rows] != list(range(1, len(rows) + 1)):
        bad.append("순위 번호가 어긋남")
    return bad


ALLOW_EN = {"jipgapradar", "kr"}          # 사이트 주소만 허용


def check_korean(texts: list[str], names: list[str]) -> list[str]:
    """카드에 찍힌 글자·캡션에 영어가 섞였는지. 단지 이름·시·구·동 이름(국토부 표기 그대로)은 빼고 본다."""
    bad = []
    for label, t in texts:
        for n in sorted({n for n in names if n}, key=len, reverse=True):
            t = t.replace(n, " ")
        words = sorted(set(re.findall(r"[A-Za-z]{2,}", t)) - ALLOW_EN)
        if words:
            bad.append(f"{label}에 영어 표기: {', '.join(words[:10])}")
    return bad
