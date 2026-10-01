"""현금 + 대출로 살 수 있는 최대 집값. 금액 단위는 만원(국토부 실거래와 같다).

규칙(수도권 무주택자의 주택 구입, 2026-10-01 확인):
- 2025-06-27 가계부채 관리 강화 방안: 수도권·규제지역 주택구입 주담대 최대 6억, 생애최초 LTV 70%, 만기 30년 이내
- 2025-10-15 주택시장 안정화 대책: 서울 25개 구 + 경기 12곳 규제지역(LTV 40%, 생애최초 70% 유지),
  규제지역 주담대 한도 15억 이하 6억 · 15~25억 4억 · 25억 초과 2억, 수도권·규제지역 스트레스 금리 3%
규칙이 바뀌면 이 파일만 고친다. 카드에는 RULES_AS_OF 를 함께 적는다.
"""
from __future__ import annotations

from dataclasses import dataclass

RULES_AS_OF = "2025.10.15 대책 기준"
# 경기 규제지역 12곳(시·구 이름은 collector 의 지역 이름과 같은 형식)
REGULATED_GG = {"과천시", "광명시", "의왕시", "하남시", "안양시 동안구", "성남시 분당구", "성남시 수정구", "성남시 중원구",
                "수원시 영통구", "수원시 장안구", "수원시 팔달구", "용인시 수지구"}
RATE = 0.04            # 가정 금리(연)
STRESS = 0.03          # 수도권·규제지역 스트레스 금리(변동금리 기준)
YEARS = 30             # 수도권·규제지역 주담대 만기 상한
DSR = 0.40             # 은행권 DSR 한도
OTHER = 0.002          # 등기·법무·채권 할인 등 기타 비용(가정)


def regulated(sido: str, gu: str) -> bool:
    return sido == "서울" or (sido == "경기" and gu in REGULATED_GG)


def ltv(is_regulated: bool, first: bool) -> float:
    if first:
        return 0.70
    return 0.40 if is_regulated else 0.70


def cap(price: float, is_regulated: bool) -> float:
    """주담대 금액 상한(수도권 6억, 규제지역은 집값 구간별로 더 낮다)."""
    if is_regulated and price > 250000:
        return 20000
    if is_regulated and price > 150000:
        return 40000
    return 60000


def dsr_limit(income: float) -> float:
    """연소득(만원)으로 받을 수 있는 최대 대출 — 원리금균등, 금리에 스트레스 금리를 더해 심사한다."""
    r = (RATE + STRESS) / 12
    n = YEARS * 12
    yearly_per_won = r / (1 - (1 + r) ** -n) * 12
    return income * DSR / yearly_per_won


def acq_tax(price: float, area: float = 84) -> float:
    """1주택 취득세 + 지방교육세(+85㎡ 초과면 농어촌특별세). 생애최초 감면은 넣지 않는다(보수적)."""
    eok = price / 10000
    if eok <= 6:
        r = 0.01
    elif eok <= 9:
        r = (eok * 2 / 3 - 3) / 100
    else:
        r = 0.03
    return price * (r * 1.1 + (0.002 if area > 85 else 0))


def brokerage(price: float) -> float:
    """매매 중개보수 상한(부가세 10% 포함)."""
    eok = price / 10000
    if price < 5000:
        fee = min(price * 0.006, 25)
    elif eok < 2:
        fee = min(price * 0.005, 80)
    elif eok < 9:
        fee = price * 0.004
    elif eok < 12:
        fee = price * 0.005
    elif eok < 15:
        fee = price * 0.006
    else:
        fee = price * 0.007
    return fee * 1.1


def costs(price: float, area: float = 84) -> float:
    return acq_tax(price, area) + brokerage(price) + price * OTHER


@dataclass
class Plan:
    price: float        # 최대 매수가
    loan: float
    costs: float
    binding: str        # 대출을 묶은 것: 'LTV' · 'DSR' · '한도'
    by_ltv: float
    by_dsr: float
    by_cap: float
    ltv: float


def loan_for(price: float, income: float, is_regulated: bool, first: bool) -> tuple[float, str, tuple]:
    a, b, c = price * ltv(is_regulated, first), dsr_limit(income), cap(price, is_regulated)
    m = min(a, b, c)
    return m, ("LTV" if m == a else "DSR" if m == b else "한도"), (a, b, c)


def max_price(cash: float, income: float, is_regulated: bool, first: bool) -> Plan:
    """현금으로 감당되는 가장 비싼 집값(이분법 — 필요한 현금은 집값에 대해 늘기만 한다)."""
    def need(p):
        return p + costs(p) - loan_for(p, income, is_regulated, first)[0]
    lo, hi = cash, 500000.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if need(mid) <= cash else (lo, mid)
    p = lo
    loan, binding, (a, b, c) = loan_for(p, income, is_regulated, first)
    return Plan(price=p, loan=loan, costs=costs(p), binding=binding, by_ltv=a, by_dsr=b, by_cap=c, ltv=ltv(is_regulated, first))


def monthly(amount: float, rate: float = RATE, years: int = YEARS) -> float:
    """원리금균등 월 상환액(실제 금리 기준, 스트레스 금리 없이)."""
    r = rate / 12
    n = years * 12
    return amount * r / (1 - (1 + r) ** -n)
