from pathlib import Path

import pytest

from collector import db
from collector.collect import months_back, pick_regions
from collector.molit import KeyProblem, QuotaExceeded, parse
from collector.normalize import record, with_uids

FX = Path(__file__).parent / "fixtures"


def test_parse_apt_sale_fields_and_units():
    page = parse((FX / "apt_sale.xml").read_text())
    assert page.total == 3 and len(page.items) == 3
    r = record("apt_sale", page.items[0], "11680")
    assert r["price"] == 245000 and r["area"] == 84.97 and r["floor"] == 12
    assert r["ymd"] == "2026-08-12" and r["name"] == "샘플마을1단지" and r["apt_seq"] == "11680-9001"
    assert r["cancelled"] == 0 and r["direct"] == 0


def test_cancelled_and_direct_deals_are_flagged():
    r = record("apt_sale", parse((FX / "apt_sale.xml").read_text()).items[1], "11680")
    assert r["cancelled"] == 1 and r["direct"] == 1


def test_villa_keeps_land_share_for_price_per_land():
    r = record("rh_sale", parse((FX / "rh_sale.xml").read_text()).items[0], "11440")
    assert r["land_area"] == 27.35 and r["house_type"] == "다세대" and r["price"] == 38500


def test_same_deal_twice_in_one_response_stays_two_but_alias_refetch_merges():
    items = parse((FX / "apt_sale.xml").read_text()).items
    recs = with_uids([record("apt_sale", it, "11680") for it in items])
    assert recs[0]["uid"] != recs[2]["uid"]          # 같은 날 같은 값 두 건은 두 건
    again = with_uids([record("apt_sale", it, "11680") for it in items])   # 옛 코드로 한 번 더 받은 경우
    assert [r["uid"] for r in recs] == [r["uid"] for r in again]


def test_error_responses_become_specific_exceptions():
    with pytest.raises(KeyProblem):
        parse((FX / "err_key.xml").read_text())
    with pytest.raises(QuotaExceeded):
        parse((FX / "err_quota.xml").read_text())
    with pytest.raises(QuotaExceeded):
        parse("API rate limit exceeded")
    # 2026-09-29 실제로 받은 응답 형식(키 없이 호출하면 HTTP 401 + 이 본문)
    with pytest.raises(KeyProblem, match="서비스 접근거부"):
        parse((FX / "err_null_key.xml").read_text())


def test_region_list_covers_all_sido_with_renamed_codes():
    rs = db.regions()
    assert len(rs) == 256
    codes = {r["code"]: r for r in rs}
    assert codes["51110"]["query"] == ["51110", "42110"]        # 강원특별자치도: 새·옛 코드 둘 다 조회
    assert codes["27720"]["sido_short"] == "대구"                # 군위군은 대구
    assert "41110" not in codes and "41111" in codes             # 구가 있는 시는 구 단위
    assert codes["36110"]["name"] == "세종시"
    assert len({r["sido_short"] for r in rs}) == 16                # 광주·전남 → 전남광주통합특별시
    assert codes["12210"]["name"] == "광주 동구" and "29110" not in codes
    assert "28125" in codes and "28110" not in codes and "41597" in codes and "41590" not in codes


def test_capital_region_comes_first_and_months_go_backwards():
    rs = pick_regions(None)
    assert rs[0]["group"] == "수도권"
    import datetime as dt
    assert months_back(3, dt.date(2026, 1, 15)) == ["202601", "202512", "202511"]


def test_encoded_and_decoded_keys_become_the_same():
    from collector.molit import Client
    import asyncio
    a, b = Client("ab%2Bcd%3D%3D"), Client("ab+cd==")
    assert a.key == b.key == "ab+cd=="
    asyncio.run(a.close()); asyncio.run(b.close())


def test_alias_codes_do_not_double_count_and_errors_skip_one_job(tmp_path, monkeypatch):
    """강원(51/42)처럼 두 코드로 같은 거래를 받으면 한 건으로, 한 작업의 서버 오류는 그 작업만 건너뛴다."""
    import asyncio
    from collector import collect
    from collector.molit import ApiError

    xml = (FX / "apt_sale.xml").read_text()

    class Fake:
        calls = __import__("collections").Counter()

        async def fetch(self, kind, lawd, ym):
            self.calls[kind] += 1
            if ym == "202607":
                raise ApiError("HTTP 500")
            return parse(xml).items

    path = tmp_path / "t.db"
    c = db.connect(path)
    jobs = [("51110", ["51110", "42110"], "202608"), ("51110", ["51110", "42110"], "202607")]
    stat = asyncio.run(collect.run_kind(Fake(), c, "apt_sale", jobs, budget=100))
    assert stat["jobs"] == 1 and stat["errors"] == 1
    assert c.execute("SELECT COUNT(*) FROM deals").fetchone()[0] == 3          # 두 코드 × 3건 → 3건
    assert db.logged(c, "apt_sale", "51110", "202608") and not db.logged(c, "apt_sale", "51110", "202607")


def test_non_xml_body_is_an_api_error():
    from collector.molit import ApiError
    with pytest.raises(ApiError):
        parse("<html><body>점검 중</body></html")
