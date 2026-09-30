"""레퍼런스(docs/DESIGN.md) 모양 그대로의 SVG 차트. 서버에서 그려 넣으므로 자바스크립트가 필요 없다.

- 막대: 끝이 둥글고, 평소 막대는 연한 세이지 빗금, 강조 막대 하나만 짙은 초록 + 위에 말풍선 칩
- 꺾은선: 부드러운 곡선 + 아래로 옅은 면 + 강조 점과 칩
- 집계 중인 달은 옅게(점선 테두리) 그린다
"""
from __future__ import annotations

import hashlib
from html import escape


def _uid(prefix: str, *content) -> str:
    """페이지 안에서만 겹치지 않으면 되는 id. 빌드 순번 대신 내용 해시를 써서, 다른 페이지가 늘어도 이 페이지는 그대로다."""
    return prefix + hashlib.sha1(repr(content).encode()).hexdigest()[:8]


def _chip(x: float, y: float, text: str) -> str:
    w = 12 + 7.2 * len(text)
    return (f'<g class="chip"><rect x="{x - w / 2:.1f}" y="{y - 26:.1f}" width="{w:.1f}" height="22" rx="11"/>'
            f'<text x="{x:.1f}" y="{y - 11:.1f}" text-anchor="middle">{escape(text)}</text></g>')


def bars(values: list[float | None], labels: list[str], *, highlight: int | None = None, chip: str | None = None,
         pending: set[int] | None = None, height: int = 210, label_every: int = 1, fmt=None, width: int = 600) -> str:
    """막대 차트. highlight 는 강조할 막대 번호(음수면 뒤에서), pending 은 '집계 중' 막대 번호."""
    n = len(values)
    if not n:
        return ""
    w, top, bottom, left = width, 34, 26, 30
    ph = height - top - bottom
    vmax = max((v or 0) for v in values) or 1
    slot = (w - left) / n
    bw = min(34, slot * 0.62)
    hid = (highlight % n) if highlight is not None else None
    pat = _uid("hatch", values, labels, width, height)
    out = [f'<svg class="chart bars" viewBox="0 0 {w} {height}" role="img" preserveAspectRatio="none">',
           f'<defs><pattern id="{pat}" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
           f'<rect width="7" height="7" class="bar-soft"/><line x1="0" y1="0" x2="0" y2="7" class="hatch-line"/></pattern></defs>']
    # 눈금 4개
    for i in range(4):
        y = top + ph * i / 3
        val = vmax * (1 - i / 3)
        out.append(f'<line x1="{left}" x2="{w}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>'
                   f'<text x="{left - 6}" y="{y + 4:.1f}" text-anchor="end" class="axis">{escape(fmt(val) if fmt else _short(val))}</text>')
    for i, v in enumerate(values):
        x = left + slot * i + (slot - bw) / 2
        h = max(bw, ph * (v or 0) / vmax) if v else 0
        y = top + ph - h
        if h:
            cls = "bar-hl" if i == hid else ("bar-pending" if pending and i in pending else "")
            fill = "" if cls else f' fill="url(#{pat})"'
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="{bw / 2:.1f}" class="{cls}"{fill}>'
                       f'<title>{escape(labels[i])}: {escape(fmt(v) if fmt else _short(v))}</title></rect>')
            if i == hid and chip:
                out.append(f'<circle cx="{x + bw / 2:.1f}" cy="{y + bw / 2:.1f}" r="4.5" class="dot"/>')
                out.append(_chip(x + bw / 2, y - 2, chip))
        if i % label_every == 0 or i == n - 1:
            out.append(f'<text x="{x + bw / 2:.1f}" y="{height - 6}" text-anchor="middle" class="axis">{escape(labels[i])}</text>')
    out.append("</svg>")
    return "".join(out)


def _poly(pts: list[tuple[float, float]]) -> str:
    """점과 점을 곧게 잇는다. 곡선 보간은 실제 없는 오르내림을 그려 넣을 수 있어 값 그래프에는 이것을 쓴다."""
    return " ".join(f"{'L' if i else 'M'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))


def _smooth(pts: list[tuple[float, float]]) -> str:
    """점들을 지나는 부드러운 곡선(카트멀-롬 → 베지어)."""
    if len(pts) < 2:
        return ""
    d = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}")
    return " ".join(d)


def area(values: list[float | None], labels: list[str], *, highlight: int | None = -1, chip: str | None = None,
         second: list[float | None] | None = None, height: int = 220, label_every: int = 1, fmt=None,
         width: int = 600) -> str:
    """꺾은선 + 면. second 가 있으면 비교선(예: 전세)을 점선으로 겹친다. 값이 없는 달은 건너뛴다."""
    n = len(values)
    known = [(i, v) for i, v in enumerate(values) if v]
    if len(known) < 2:
        return ""
    w, top, bottom, left = width, 40, 26, 44
    ph = height - top - bottom
    allv = [v for _, v in known] + [v for v in (second or []) if v]
    lo, hi = min(allv), max(allv)
    pad = (hi - lo) * 0.18 or hi * 0.1 or 1
    lo, hi = lo - pad, hi + pad
    sx = lambda i: left + (w - left - 8) * (i / max(1, n - 1))
    sy = lambda v: top + ph * (1 - (v - lo) / (hi - lo))
    pts = [(sx(i), sy(v)) for i, v in known]
    gid = _uid("fade", values, second, labels, width, height)
    path = _poly(pts)
    out = [f'<svg class="chart area" viewBox="0 0 {w} {height}" role="img" preserveAspectRatio="none">',
           f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" class="fade-top"/>'
           f'<stop offset="1" class="fade-bottom"/></linearGradient></defs>']
    for i in range(4):
        y = top + ph * i / 3
        val = hi - (hi - lo) * i / 3
        out.append(f'<line x1="{left}" x2="{w}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>'
                   f'<text x="{left - 6}" y="{y + 4:.1f}" text-anchor="end" class="axis">{escape(fmt(val) if fmt else _short(val))}</text>')
    out.append(f'<path d="{path} L{pts[-1][0]:.1f},{top + ph} L{pts[0][0]:.1f},{top + ph} Z" fill="url(#{gid})"/>')
    if second:
        sp = [(sx(i), sy(v)) for i, v in enumerate(second) if v]
        if len(sp) >= 2:
            out.append(f'<path d="{_poly(sp)}" class="line-2"/>')
    out.append(f'<path d="{path}" class="line"/>')
    if highlight is not None and known:
        hi_i = highlight % n
        cand = [p for p in known if p[0] <= hi_i]
        i, v = cand[-1] if cand else known[-1]
        x, y = sx(i), sy(v)
        out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y:.1f}" y2="{top + ph}" class="guide"/>')
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" class="dot"/>')
        if chip:
            out.append(_chip(min(max(x, 60), w - 60), y - 6, chip))
    for i, lab in enumerate(labels):
        if i % label_every == 0 or i == n - 1:
            out.append(f'<text x="{sx(i):.1f}" y="{height - 6}" text-anchor="middle" class="axis">{escape(lab)}</text>')
    out.append("</svg>")
    return "".join(out)


def scatter(points: list[dict], months: list[str], *, med: list[float | None] | None = None, height: int = 260,
            label_every: int = 6, fmt=None, width: int = 600, month_label=None) -> str:
    """거래 한 건 = 점 하나. points: {ym, day(1~31), price, cls, title}. cls 는 lo·mid·hi(층) · x(해제) · dir(직거래) · out(확인 필요).
    med 는 달마다 중위값(선). 평균선만 보여 주는 대신 모든 거래를 그대로 보여 주려는 차트."""
    if not points or not months:
        return ""
    idx = {m: i for i, m in enumerate(months)}
    pts = [p for p in points if p["ym"] in idx]
    if not pts:
        return ""
    w, top, bottom, left = width, 16, 26, 44
    ph = height - top - bottom
    vals = [p["price"] for p in pts] + [v for v in (med or []) if v]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.1 or hi * 0.05 or 1
    lo, hi = lo - pad, hi + pad
    n = len(months)
    colw = (w - left - 8) / n
    sx = lambda m, day: left + colw * (idx[m] + (min(day, 30) - 0.5) / 30)
    sy = lambda v: top + ph * (1 - (v - lo) / (hi - lo))
    out = [f'<svg class="chart scatter" viewBox="0 0 {w} {height}" role="img" preserveAspectRatio="none">']
    for i in range(4):
        y = top + ph * i / 3
        val = hi - (hi - lo) * i / 3
        out.append(f'<line x1="{left}" x2="{w}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>'
                   f'<text x="{left - 6}" y="{y + 4:.1f}" text-anchor="end" class="axis">{escape(fmt(val) if fmt else _short(val))}</text>')
    if med:
        mp = [(left + colw * (i + 0.5), sy(v)) for i, v in enumerate(med) if v]
        if len(mp) >= 2:
            out.append(f'<path d="{_poly(mp)}" class="med"/>')
    order = {"x": 0, "dir": 1, "out": 2, "lo": 3, "mid": 3, "hi": 3}
    for p in sorted(pts, key=lambda p: order.get(p["cls"], 3)):
        x, y = sx(p["ym"], p["day"]), sy(p["price"])
        t = f'<title>{escape(p["title"])}</title>'
        if p["cls"] == "x":
            out.append(f'<path d="M{x - 3.5:.1f},{y - 3.5:.1f}l7,7m0,-7l-7,7" class="pt x">{t}</path>')
        else:
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.6" class="pt {p["cls"]}">{t}</circle>')
    for i, m in enumerate(months):
        if i % label_every == 0 or i == n - 1:
            lab = month_label(m) if month_label else m
            out.append(f'<text x="{left + colw * (i + 0.5):.1f}" y="{height - 6}" text-anchor="middle" class="axis">{escape(lab)}</text>')
    out.append("</svg>")
    return "".join(out)


def gap_bars(rows: list[tuple], *, height: int = 200, width: int = 600, fmt=None) -> str:
    """분기별 매매 중위(막대 전체)와 신규 전세 중위(아래 칠한 부분). 위에 남는 부분이 갭."""
    rows = [r for r in rows if r[2]]
    if len(rows) < 2:
        return ""
    w, top, bottom, left = width, 14, 26, 44
    ph = height - top - bottom
    vmax = max(r[2] for r in rows) * 1.05
    slot = (w - left) / len(rows)
    bw = min(26, slot * 0.6)
    out = [f'<svg class="chart gap" viewBox="0 0 {w} {height}" role="img" preserveAspectRatio="none">']
    for i in range(4):
        y = top + ph * i / 3
        val = vmax * (1 - i / 3)
        out.append(f'<line x1="{left}" x2="{w}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>'
                   f'<text x="{left - 6}" y="{y + 4:.1f}" text-anchor="end" class="axis">{escape(fmt(val) if fmt else _short(val))}</text>')
    every = max(1, len(rows) // 6)
    for i, (q, gap, sale, jeonse) in enumerate(rows):
        x = left + slot * i + (slot - bw) / 2
        hs = ph * sale / vmax
        out.append(f'<rect x="{x:.1f}" y="{top + ph - hs:.1f}" width="{bw:.1f}" height="{hs:.1f}" class="g-sale">'
                   f'<title>{q} 매매 {escape(fmt(sale) if fmt else _short(sale))}</title></rect>')
        if jeonse:
            hj = ph * jeonse / vmax
            out.append(f'<rect x="{x:.1f}" y="{top + ph - hj:.1f}" width="{bw:.1f}" height="{hj:.1f}" class="g-jeonse">'
                       f'<title>{q} 신규 전세 {escape(fmt(jeonse) if fmt else _short(jeonse))} · 갭 {escape(fmt(gap) if fmt else _short(gap))}</title></rect>')
        if i % every == 0 or i == len(rows) - 1:
            out.append(f'<text x="{x + bw / 2:.1f}" y="{height - 6}" text-anchor="middle" class="axis">{escape(q)}</text>')
    out.append("</svg>")
    return "".join(out)


def labeled_line(values: list[float | None], labels: list[str], *, counts: list[int] | None = None, height: int = 240,
                 width: int = 600, fmt=None, label_every: int = 3, tick_every: int = 3) -> str:
    """값이 찍힌 꺾은선(최고·최저·마지막은 항상, 나머지는 label_every 마다) + 아래 거래량 막대. 설명 없이 숫자로 읽히게."""
    n = len(values)
    known = [(i, v) for i, v in enumerate(values) if v]
    if len(known) < 2:
        return ""
    w, top, bottom, left, right = width, 30, 30, 8, 8
    vol_h = 34 if counts else 0
    ph = height - top - bottom - vol_h
    lo, hi = min(v for _, v in known), max(v for _, v in known)
    pad = (hi - lo) * 0.12 or hi * 0.05 or 1
    lo, hi = lo - pad, hi + pad
    sx = lambda i: left + 14 + (w - left - right - 28) * (i / max(1, n - 1))
    sy = lambda v: top + ph * (1 - (v - lo) / (hi - lo))
    pts = [(sx(i), sy(v)) for i, v in known]
    out = [f'<svg class="chart lline" viewBox="0 0 {w} {height}" role="img" preserveAspectRatio="none">']
    if counts:
        cmax = max(counts) or 1
        bw = max(3, (w - left - right) / n * 0.5)
        base = height - bottom
        for i, c in enumerate(counts):
            if c:
                h = vol_h * 0.9 * c / cmax
                out.append(f'<rect x="{sx(i) - bw / 2:.1f}" y="{base - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="1.5" class="vol">'
                           f'<title>{escape(labels[i])} {c}건</title></rect>')
    out.append(f'<path d="{_poly(pts)}" class="line"/>')
    i_max = max(known, key=lambda p: p[1])[0]
    i_min = min(known, key=lambda p: p[1])[0]
    i_last = known[-1][0]
    for k, (i, v) in enumerate(known):
        x, y = sx(i), sy(v)
        cls = "dot hi" if i == i_max else "dot lo" if i == i_min else "dot last" if i == i_last else "dot"
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{5 if i in (i_max, i_min, i_last) else 3.2}" class="{cls}">'
                   f'<title>{escape(labels[i])} {escape(fmt(v) if fmt else _short(v))}</title></circle>')
        em = i in (i_max, i_min, i_last)
        near_em = any(abs(i - j) <= 1 for j in (i_max, i_min, i_last))
        if em or (k % label_every == 0 and not near_em):
            txt = escape((fmt(v) if fmt else _short(v)).replace("억", ""))
            ty = y + 17 if i == i_min else y - 10
            out.append(f'<text x="{x:.1f}" y="{ty:.1f}" text-anchor="middle" class="val{" em" if i in (i_max, i_min, i_last) else ""}">{txt}</text>')
    for i, lab in enumerate(labels):
        if i % tick_every == 0 or i == n - 1:
            out.append(f'<text x="{sx(i):.1f}" y="{height - 8}" text-anchor="middle" class="axis">{escape(lab)}</text>')
    out.append("</svg>")
    return "".join(out)


def spark(values: list[float | None], *, up_is: str = "up") -> str:
    """목록 행 오른쪽의 작은 추세선."""
    known = [(i, v) for i, v in enumerate(values) if v]
    if len(known) < 2:
        return ""
    w, h = 84, 28
    lo, hi = min(v for _, v in known), max(v for _, v in known)
    rng = (hi - lo) or 1
    n = len(values)
    pts = [(2 + (w - 4) * i / max(1, n - 1), 3 + (h - 6) * (1 - (v - lo) / rng)) for i, v in known]
    trend = "up" if known[-1][1] >= known[0][1] else "down"
    return (f'<svg class="spark {trend}" viewBox="0 0 {w} {h}" aria-hidden="true">'
            f'<path d="{_poly(pts)}"/></svg>')


def stages(n_total: int, current: int | None) -> str:
    """재개발 추진 단계 막대(현재 단계까지 채움)."""
    out = ['<div class="stages">']
    for i in range(n_total):
        cls = "done" if current is not None and i < current else ("now" if i == current else "")
        out.append(f'<span class="{cls}"></span>')
    out.append("</div>")
    return "".join(out)


def _short(v: float | None) -> str:
    if v is None:
        return ""
    if v >= 10000:
        return f"{v / 10000:.1f}억".replace(".0억", "억")
    if v >= 1000:
        return f"{v / 1000:.1f}천".replace(".0천", "천")
    return f"{v:.0f}"
