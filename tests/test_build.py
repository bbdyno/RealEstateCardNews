import datetime as dt
import json

import pytest

from collector import db, demo
from web import build


@pytest.fixture()
def demo_db(tmp_path, monkeypatch):
    path = tmp_path / "t.db"
    real = db.connect
    monkeypatch.setattr(db, "connect", lambda p=path: real(p))
    c = db.connect()
    deals, zones = demo.gen(months=14, end=dt.date(2026, 9, 29))
    db.upsert(c, deals, demo=1)
    c.executemany(f"INSERT INTO redevelop({','.join(demo.ZCOLS)}) VALUES({','.join('?' * len(demo.ZCOLS))})",
                  [tuple(z[k] for k in demo.ZCOLS) for z in zones])
    c.commit()
    return path


def test_demo_build_is_complete_and_never_indexable(demo_db, tmp_path):
    out = tmp_path / "dist"
    info = build.build(out, dt.date(2026, 9, 29))
    assert info["demo"] and info["regions_with_data"] == len(demo.REGIONS)
    home = (out / "index.html").read_text()
    assert 'name="robots" content="noindex' in home and "샘플 데이터" in home
    assert (out / "robots.txt").read_text().startswith("User-agent: *\nDisallow: /")
    assert (out / "r" / "11680" / "index.html").exists() and (out / "redevelop" / "index.html").exists()
    idx = json.loads((out / "search.json").read_text())
    assert any(row[2] == "/r/11680/" for row in idx)
    assert "<loc>" in (out / "sitemap.xml").read_text()


def test_big_sitemaps_are_split_into_an_index(tmp_path):
    build.write_sitemaps(tmp_path, "https://x.kr", [f"/c/{i}/" for i in range(5)], chunk=2)
    idx = (tmp_path / "sitemap.xml").read_text()
    assert "<sitemapindex" in idx and idx.count("<sitemap>") == 3
    assert (tmp_path / "sitemap-3.xml").read_text().count("<url>") == 1


def test_breadcrumbs_become_structured_data():
    html = '<div class="crumbs"><a href="/">전국</a> › <a href="/r/11/">서울</a> › 강남구</div><h1>x</h1>'
    out = build.breadcrumb_ld(html, "https://x.kr")
    ld = json.loads(out.split('application/ld+json">')[1].split("</script>")[0])
    assert [e["name"] for e in ld["itemListElement"]] == ["전국", "서울", "강남구"]
    assert ld["itemListElement"][1]["item"] == "https://x.kr/r/11/" and "item" not in ld["itemListElement"][2]


def _complex_pages(out):
    return [p for p in (out / "c").glob("*/index.html")]


def test_no_ad_markup_until_ids_are_configured(demo_db, tmp_path):
    out = tmp_path / "dist"
    build.build(out, dt.date(2026, 9, 29))
    html = "".join(p.read_text() for p in _complex_pages(out)[:20]) + (out / "index.html").read_text()
    assert "ad-slot" not in html and "adsbygoogle" not in html and "쿠팡 파트너스 활동" not in html


def test_adsense_slot_carries_adfit_fallback(demo_db, tmp_path, monkeypatch):
    cfg = build.load_cfg()
    cfg["ads"]["adsense"] = {"client": "ca-pub-1", "slots": {"top": "111", "mid": "", "bottom": "333"}}
    cfg["ads"]["adfit"] = {"units": {"top": {}, "mid": {}, "bottom": {"id": "DAN-x", "w": 300, "h": 250}}}
    monkeypatch.setattr(build, "load_cfg", lambda: cfg)
    out = tmp_path / "dist"
    build.build(out, dt.date(2026, 9, 29))
    page = max(_complex_pages(out), key=lambda p: p.stat().st_size).read_text()   # 거래 많은 단지(광고 최대)
    assert page.count('class="adsbygoogle"') == 2
    assert 'data-ad-slot="333" data-ad-format="auto" data-full-width-responsive="true" data-fallback="DAN-x:300x250"' in page
    assert (out / "ads.txt").read_text().startswith("google.com, pub-1, DIRECT")


def test_sponsors_run_only_in_their_window_and_region(tmp_path):
    f = tmp_path / "sponsors.yaml"
    f.write_text("""sponsors:
  - {id: a, advertiser: A, title: 전국, url: "https://a", start: 2026-09-01, end: 2026-09-30}
  - {id: b, advertiser: B, title: 동탄, url: "https://b", start: 2026-09-01, end: 2026-10-31, regions: ["41597"]}
  - {id: c, advertiser: C, title: 지난 광고, url: "https://c", start: 2026-08-01, end: 2026-08-31}
""", encoding="utf-8")
    live = build.load_sponsors(dt.date(2026, 9, 29), f)
    assert [s["id"] for s in live] == ["a", "b"]
    site = build.Site.__new__(build.Site)
    site.sponsors = live
    assert site.sponsor("41597")["id"] == "b"          # 좁은 지역 계약이 먼저
    assert site.sponsor("11680")["id"] == "a"
    assert build.load_sponsors(dt.date(2026, 10, 5), f)[0]["id"] == "b"
