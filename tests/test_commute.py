"""업무지구 출퇴근 릴스(cards/commute.py · reels/build.py 의 commute 부분) — DB·엔진 없이 도는 부분만."""
import datetime as dt

from analytics.core import Complex
from cards import check, commute
from cards.commute import Episode
from reels import build

TODAY = dt.date(2026, 10, 28)


def sale(ymd, price, area=59.9, cancelled=0, direct=0):
    return {"ymd": ymd, "price": price, "area": area, "cancelled": cancelled, "direct": direct}


def cx(name, umd, sales, year=2005, cid=None):
    c = Complex(cid=cid or name, kind="apt", sgg="11470", umd=umd, jibun="1", name=name, build_year=year)
    c.sales = sorted(sales, key=lambda s: s["ymd"], reverse=True)
    return c


OLD = [sale(f"2024-0{m}-10", 80000) for m in range(1, 9)]        # 3년 거래 10건을 채우는 옛 거래


def test_candidates_rules():
    area = {"umd": ["신정동"], "lines": ["5"], "min": [15, 25]}
    keep = cx("신트리4", "신정동", OLD + [sale("2026-09-01", 89000), sale("2026-09-20", 87000), sale("2026-10-01", 91000)])
    few = cx("적은단지", "신정동", OLD + [sale("2026-09-01", 89000), sale("2026-09-20", 87000)])          # 6개월 2건
    rent = cx("신정임대", "신정동", OLD + [sale("2026-09-01", 89000)] * 3)                                   # 임대 이름
    away = cx("다른동", "목동", OLD + [sale("2026-09-01", 89000)] * 3)                                       # 권역 밖 동
    cut = cx("해제많음", "신정동", OLD + [sale("2026-09-01", 89000), sale("2026-09-02", 89000, cancelled=1),
                                    sale("2026-09-03", 89000, direct=1), sale("2026-09-04", 89000)])        # 해제·직거래 빼면 2건
    rows = commute.candidates_from([keep, few, rent, away, cut], area, "양천구", TODAY)
    assert [r["name"] for r in rows] == ["신트리4"]
    r = rows[0]
    assert r["size"] == "59형" and r["n"] == 3 and r["median"] == 89000 and r["lo"] == 87000 and r["hi"] == 91000
    assert r["line"] == "5호선" and r["href"] == "/c/신트리4/" and r["last_ymd"] == "2026-10-01"


def test_titles_and_josa():
    assert Episode("budget", "여의도", "8~9억", "59형").title == "여의도 출근 8~9억 59형"
    assert Episode("new", "성수", size="84형").title == "성수 출근 신축 84형"
    assert Episode("dual", "여의도", size="59형", hub2="구디·가산").title == "맞벌이 여의도+구디·가산 59형"
    assert commute.josa("가산", "이라면", "라면") == "이라면" and commute.josa("여의도", "이라면", "라면") == "라면"


def test_labels():
    assert commute.line_label(["5", "7", "신림"]) == "5·7호선·신림선"
    assert commute.line_label(["공항", "9"]) == "9호선·공항철도"
    assert commute.band_of(89999) == "8~9억" and commute.band_of(90000) == "9~10억" and commute.band_of(39000) is None
    assert commute.size_of(59.9) == "59형" and commute.size_of(84.97) == "84형" and commute.size_of(70) is None


def test_episodes_cover_every_hub_and_rotate():
    eps = commute.all_episodes()
    names = {h["name"] for h in commute.hubs()}
    assert {e.hub for e in eps} == names
    assert len({e.key for e in eps}) == len(eps)                       # 같은 편이 두 번 없다
    first = eps[:len(names)]
    assert len({e.hub for e in first if e.kind == "budget"}) == len([e for e in first if e.kind == "budget"])  # 처음 몇 편은 업무지구가 다 다르다


def test_order_puts_unposted_first():
    eps = commute.all_episodes()[:4]
    log = [{"title": eps[0].title, "at": "2026-10-27T12:10"}, {"title": eps[2].title, "at": "2026-10-26T12:10"}]
    out = commute.order(log, eps)
    assert out[:2] == [eps[1], eps[3]]                                  # 안 나온 편 먼저(목록 순)
    assert out[2:] == [eps[2], eps[0]]                                  # 그다음 오래전에 나온 순


def row(rank, name, median, n=5, built=2005, mins=(15, 25), last="2026-10-01", **kw):
    return dict(rank=rank, name=name, gu="양천구", umd="신정동", cid=name, built=built, size="59형", area=59, n=n,
                median=median, lo=median - 5000, hi=median + 5000, last_ymd=last, last_price=median, lines=["5"],
                line="5호선", to="여의도", min=list(mins), href=f"/c/{name}/", **kw)


def test_check_commute():
    ep = Episode("budget", "여의도", "8~9억", "59형")
    good = [row(i, f"단지{i}", 85000) for i in range(1, 6)]
    assert check.check_commute(good, ep, TODAY) == []
    bad = good[:4] + [row(5, "단지1", 95000, n=2, last="2026-01-01")]
    out = check.check_commute(bad, ep, TODAY)
    assert any("8~9억 밖" in b for b in out) and any("3건 미만" in b for b in out)
    assert any("6개월 밖" in b for b in out) and any("중복" in b for b in out)
    assert check.check_commute(good[:3], ep, TODAY)[0].startswith("단지가 3곳뿐")
    new = Episode("new", "성수", size="59형")
    assert any("신축 조건 밖" in b for b in check.check_commute(good, new, TODAY))


def test_summary_merges_same_complex():
    rows = [row(1, "가", 87000, built=2007, mins=(20, 30)), row(2, "나", 81000, built=1996, mins=(5, 15))]
    s = build.summary(rows)
    assert [x["v"] for x in s] == ["나", "가"]
    assert s[0]["k"] == "가장 가깝고 중앙값도 가장 낮은 곳" and s[1]["k"] == "가장 새 아파트"


def test_plan_commute_bars():
    c = build.plan_commute(5)
    assert c["r5"] == 4.8 and c["r1"] == 14.4 and c["sum"] == 19.2 and c["outro"] == 21.6 and c["end"] == 26.4
    spec = build.music_commute(c, 5)
    assert all(0 <= e["t"] < c["end"] for e in spec["events"])
    assert any(e["type"] == "boom" and e["t"] == c["r1"] for e in spec["events"])


def test_commute_slug_is_ascii():
    for ep in commute.all_episodes():
        slug = build.commute_slug(ep)
        assert slug.isascii() and slug.startswith("commute-")
    assert len({build.commute_slug(e) for e in commute.all_episodes()}) == len(commute.all_episodes())


def test_commute_rows_strings():
    r = build.commute_rows([row(1, "신트리4", 89000, n=10)])[0]
    assert r["median_label"] == "8억 9,000만" and r["min_label"] == "약 15~25분"
    assert r["commute"] == "5호선 → 여의도" and r["lines"] == [{"t": "5", "c": "#996CAC"}]
    d = build.commute_rows([row(1, "가", 90000, to2="강남·삼성", line2="2호선", lines2=["2"], min2=[15, 25])])[0]
    assert d["min_label"] == "둘 다 25분 안" and d["commute2"] == "→ 강남·삼성 약 15~25분"


def test_youtube_helpers_and_off_without_keys(monkeypatch, tmp_path):
    from cards import youtube
    for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    assert youtube.upload_short(tmp_path / "x.mp4", "제목") is None            # 키가 없으면 아무것도 안 한다
    assert youtube.title_from("가" * 120 + "\n둘째 줄").endswith("…") and len(youtube.title_from("가" * 120)) == 100
    assert youtube.tags_from("본문 #여의도출퇴근 #8억대아파트") == ["여의도출퇴근", "8억대아파트"]


def test_caption_every_kind():
    from cards import post
    rows = [row(i, f"단지{i}", 85000, n=10 - i) for i in range(1, 6)]
    dual = [dict(r, to2="강남·삼성", line2="2호선", lines2=["2"], min2=[15, 25]) for r in rows]
    for ep, rs in [(Episode("budget", "여의도", "8~9억", "59형"), rows), (Episode("new", "성수", size="84형"), rows),
                   (Episode("dual", "여의도", size="59형", hub2="강남"), dual)]:
        cap = post.commute_caption(ep, rs, rs, TODAY)
        assert cap.startswith(ep.title) and check.check_caption(cap, []) == []
        assert check.check_korean([("캡션", cap)], [x[k] for x in rs for k in ("name", "gu", "umd")]) == []
    assert "강남이라면?" in post.commute_caption(Episode("dual", "여의도", size="59형", hub2="강남"), dual, dual, TODAY)
