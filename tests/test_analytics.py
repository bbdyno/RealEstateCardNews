import datetime as dt

from analytics import core
from web import fmt


def _sale(ymd, price, area=84.9, cancelled=0, name="가단지"):
    return {"kind": "apt", "trade": "sale", "sgg": "11680", "umd": "가동", "jibun": "1", "name": name, "apt_seq": "11680-1",
            "area": area, "land_area": None, "floor": 5, "build_year": 2010, "ymd": ymd, "price": price, "deposit": None,
            "rent": None, "contract": None, "house_type": None, "cancelled": cancelled, "direct": 0}


def _rent(ymd, deposit, rent=0, area=84.9, kind="apt", name="가단지"):
    d = _sale(ymd, None, area, name=name)
    d.update({"trade": "rent", "kind": kind, "deposit": deposit, "rent": rent, "apt_seq": None})
    return d


def test_base_month_waits_for_reporting_lag():
    assert core.base_month(dt.date(2026, 9, 29)) == "2026-08"
    assert core.base_month(dt.date(2026, 9, 5)) == "2026-07"
    assert core.base_month(dt.date(2026, 1, 25)) == "2025-12"


def test_new_high_needs_an_earlier_deal_and_ignores_cancelled():
    rows = [_sale("2025-01-10", 100000), _sale("2026-08-01", 105000), _sale("2026-08-20", 120000, cancelled=1),
            _sale("2026-09-01", 99000, area=59.9)]
    cx = core.build_complexes(rows, "apt")
    highs = core.new_highs(cx, "2026-07-01")
    assert [h["deal"]["price"] for h in highs] == [105000]      # 해제된 12억은 빼고, 59㎡ 첫 거래는 신고가 아님
    c = next(iter(cx.values()))
    assert c.last_sale["price"] == 99000 and c.peak["price"] == 99000   # 최근 거래(59㎡) 기준 같은 면적 최고가


def test_jeonse_ratio_uses_same_band_and_only_jeonse():
    rows = [_sale("2026-06-01", 100000), _rent("2026-06-05", 60000), _rent("2026-06-06", 5000, rent=150)]
    c = next(iter(core.build_complexes(rows, "apt").values()))
    assert abs(c.jeonse_ratio - 0.6) < 1e-9                     # 월세 계약은 빠진다


def test_officetel_yield_is_annual_rent_over_net_investment():
    rows = [dict(_sale("2026-05-01", 20000, 24.5, name="오"), kind="offi", apt_seq=None),
            _rent("2026-05-02", 1000, 80, 24.5, "offi", "오")]
    o = next(iter(core.build_complexes(rows, "offi").values()))
    assert abs(o.yield_ - 80 * 12 / (20000 - 1000)) < 1e-9


def test_size_bands_and_labels():
    assert core.band(59.9) == "20평대" and core.band(84.9) == "30평대" and core.band(49.8) == "10평대"
    assert fmt.ptype(84.97) == "34평형" and fmt.ptype(59.99) == "24평형" and fmt.ptype(24.5, "offi") == "전용 24㎡"


def test_money_formats():
    assert fmt.won(245000) == "24억 5,000만" and fmt.won(250000) == "25억" and fmt.won(9800) == "9,800만"
    assert fmt.eok(245000) == "24.5억" and fmt.eok(79500) == "7.95억"
    assert fmt.big(79500) == ("7", ".95억") and fmt.big(80000) == ("8", "억")
    assert fmt.pct(-0.021) == "−2.1%" and fmt.pct(0.119) == "+11.9%"


def test_rent_with_spacing_difference_joins_the_same_complex():
    rows = [_sale("2026-06-01", 100000, name="가나 다라"), _rent("2026-06-05", 60000, name="가나다라")]
    cxs = core.build_complexes(rows, "apt")
    assert len(cxs) == 1 and len(next(iter(cxs.values())).rents) == 1


def test_lone_outlier_trades_do_not_drive_peak_or_drop():
    """타워팰리스2·제각말 사례: 같은 면적에서 혼자 동떨어진 거래는 가격 통계에서 빠진다."""
    tp = [_sale(d, p, 165.0) for d, p in [("2024-07-10", 455000), ("2024-12-21", 470000), ("2025-01-12", 460000),
                                         ("2025-03-23", 475000), ("2025-05-15", 472000), ("2026-07-31", 525000),
                                         ("2026-08-11", 355000)]]
    c = next(iter(core.build_complexes(tp, "apt").values()))
    assert c.last_sale["price"] == 525000 and c.peak["price"] == 525000     # 35.5억(혼자 −24%)은 확인 필요
    assert [x["price"] for x in c.sales if x.get("outlier")] == [355000]
    jg = [_sale(d, p, 102.0) for d, p in [("2025-05-13", 110000), ("2025-07-03", 101000), ("2026-04-02", 193000),
                                         ("2026-08-10", 100000)]]
    c2 = next(iter(core.build_complexes(jg, "apt").values()))
    assert c2.peak["price"] == 110000 and round(c2.drop, 3) == round(100000 / 110000 - 1, 3)


def test_direct_deals_count_as_volume_but_not_price():
    rows = [_sale("2026-08-01", 100000), _sale("2026-08-02", 101000), dict(_sale("2026-08-03", 50000), direct=1)]
    st = core.region_stats(rows, "apt", dt.date(2026, 9, 29))
    assert st.count_base == 3 and st.median_price == 100500
    c = next(iter(core.build_complexes(rows, "apt").values()))
    assert c.last_sale["price"] == 101000
