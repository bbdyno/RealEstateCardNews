from cards import check, loan
from cards.post import won


def test_dsr_binds_for_typical_newlywed():
    p = loan.max_price(20000, 8000, True, True)          # 현금 2억 · 연소득 8천 · 생애최초 · 서울
    assert p.binding == "DSR"
    assert 39000 < p.loan < 41000                        # 금리 4%+스트레스 3%, 30년 → 약 4억
    assert 58000 < p.price < 60000
    assert check.check_plan(20000, p) == []


def test_regulated_non_first_ltv_40():
    p = loan.max_price(20000, 8000, True, False)
    assert p.binding == "LTV" and abs(p.ltv - 0.4) < 1e-9
    assert p.price < loan.max_price(20000, 8000, False, False).price


def test_cap_by_price_band():
    assert loan.cap(140000, True) == 60000
    assert loan.cap(200000, True) == 40000
    assert loan.cap(300000, True) == 20000
    assert loan.cap(300000, False) == 60000


def test_regulated_regions():
    assert loan.regulated("서울", "강북구")
    assert loan.regulated("경기", "성남시 분당구")
    assert not loan.regulated("경기", "김포시")
    assert not loan.regulated("인천", "연수구")


def test_acq_tax_steps():
    assert abs(loan.acq_tax(50000) - 50000 * 0.011) < 1
    assert abs(loan.acq_tax(100000) - 100000 * 0.033) < 1
    assert loan.acq_tax(60000) < loan.acq_tax(75000) < loan.acq_tax(90000)


def test_monthly_payment():
    assert 190 < loan.monthly(40000) < 192                 # 4억 · 4% · 30년 ≈ 191만 원


def test_won_text():
    assert won(8000) == "8천만 원"
    assert won(12000) == "1억 2천만 원"
    assert won(30000) == "3억 원"
