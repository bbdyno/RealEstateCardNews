"""숫자·날짜 표기(국내 부동산 서비스 관례). 금액 입력은 모두 만원 단위."""
from __future__ import annotations

PY = 3.3058


def num(v, digits: int = 0) -> str:
    if v is None:
        return "–"
    return f"{v:,.{digits}f}"


def won(v) -> str:
    """245000 → '24억 5,000만', 98000 → '9억 8,000만', 9800 → '9,800만', 250000 → '25억'."""
    if v is None:
        return "–"
    v = int(round(v))
    eok, man = divmod(v, 10000)
    if eok and man:
        return f"{eok}억 {man:,}만"
    if eok:
        return f"{eok}억"
    return f"{man:,}만"


def eok(v) -> str:
    """표·칩용 짧은 표기: 245000 → '24.5억', 9800 → '9,800만'."""
    if v is None:
        return "–"
    if v >= 10000:
        s = f"{v / 10000:.2f}".rstrip("0").rstrip(".")
        return f"{s}억"
    return f"{int(round(v)):,}만"


def eokn(v) -> str:
    """표 안 숫자(단위 억 고정): 245000 → '24.5', 9800 → '0.98'."""
    if v is None:
        return "–"
    return f"{v / 10000:.2f}".rstrip("0").rstrip(".")


def big(v) -> tuple[str, str]:
    """큰 숫자 표시용 (앞자리, 뒤 흐린 부분). 레퍼런스처럼 뒷자리·단위만 작고 흐리게."""
    if v is None:
        return ("–", "")
    if v >= 10000:
        whole, frac = divmod(round(v / 100), 100)      # 0.01억(100만) 단위 — 표의 eok() 와 같은 자릿수
        return (f"{whole:,}", f".{frac:02d}".rstrip("0") + "억" if frac else "억")
    return (f"{int(round(v)):,}", "만원")


def pct(v, sign: bool = True, digits: int = 1) -> str:
    if v is None:
        return "–"
    s = f"{v * 100:.{digits}f}%"
    if sign and v > 0:
        s = "+" + s
    return s.replace("-", "−")


def ratio(v) -> str:
    return "–" if v is None else f"{v * 100:.0f}%"


def delta(v) -> str:
    """상승·하락 클래스(국내 관례: 상승=빨강, 하락=파랑 — 색은 CSS 변수로)."""
    if v is None or abs(v) < 0.0005:
        return "flat"
    return "up" if v > 0 else "down"


def arrow(v) -> str:
    return {"up": "▲", "down": "▼"}.get(delta(v), "")


def pyeong(area) -> str:
    return "–" if not area else f"{area / PY:.1f}평"


def ptype(area, kind: str = "apt") -> str:
    """아파트·분양권: 공급 평형 어림(전용 × 1.33 ÷ 3.3058, 전용률 75% 가정) → '34평형'. 그 밖: '전용 25㎡'."""
    if not area:
        return "–"
    if kind in ("apt", "silv"):
        return f"{round(area * 1.33 / PY)}평형"
    return f"전용 {area:.0f}㎡"


def sqm(area) -> str:
    return "–" if not area else f"{area:.2f}㎡".replace(".00㎡", "㎡")


def date(ymd: str | None) -> str:
    """'2026-09-25' → '26.09.25'."""
    return "–" if not ymd else f"{ymd[2:4]}.{ymd[5:7]}.{ymd[8:10]}"


def month(ym: str) -> str:
    """'2026-08' → '8월', 1월은 연도를 붙여 '26.1월'."""
    y, m = ym[:4], int(ym[5:7])
    return f"’{y[2:]}.1월" if m == 1 else f"{m}월"


def month_long(ym: str) -> str:
    return f"{ym[:4]}년 {int(ym[5:7])}월"


def age(build_year, today_year: int) -> str:
    return "–" if not build_year else f"{today_year - build_year + 1}년차"


FILTERS = {"num": num, "won": won, "eok": eok, "eokn": eokn, "pct": pct, "ratio": ratio, "delta": delta, "arrow": arrow,
           "pyeong": pyeong, "ptype": ptype, "sqm": sqm, "date": date, "month": month, "month_long": month_long}
