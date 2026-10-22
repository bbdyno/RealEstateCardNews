"""서울 구 순번(cards/post.py gu_order) — 25개 구를 중복 없이 한 바퀴 돈 뒤 다음 바퀴로. DB·네트워크 없이."""
from cards import post

CODES = [f"c{i:02d}" for i in range(25)]
NAMES = {c: f"구{i:02d}구" for i, c in enumerate(CODES)}


def order(log):
    return post.gu_order(log, CODES, NAMES.get)


def entry(code, at, series="dong", band="30평형"):
    title = f"{NAMES[code]} 동별 대표 아파트 " + ("릴스" if series == "reelday" else band)
    return {"date": at[:10], "at": at, "series": series, "title": title}


def test_unshown_gus_come_first_in_code_order():
    log = [entry("c03", "2026-10-08T10:11"), entry("c01", "2026-10-09T10:11")]
    out = order(log)
    assert out[:3] == ["c00", "c02", "c04"]
    assert out[-2:] == ["c03", "c01"]                      # 나온 구는 오래된 것부터, 맨 뒤로


def test_full_round_without_repeat_then_next_round_in_same_order():
    log, seen = [], []
    for day in range(50):
        gu = order(log)[0]
        seen.append(gu)
        log.append(entry(gu, f"2026-11-{day // 24 + 1:02d}T{day % 24:02d}:00"))
    assert sorted(seen[:25]) == CODES                      # 첫 바퀴: 25개 모두 한 번씩
    assert seen[25:] == seen[:25]                          # 둘째 바퀴: 같은 순서로 다시


def test_reel_and_20py_count_as_shown_but_other_titles_do_not():
    log = [entry("c00", "2026-10-10T18:11", series="reelday"), entry("c01", "2026-10-11T14:41", series="dong2", band="20평형"),
           {"date": "2026-10-12", "at": "2026-10-12T08:10", "series": "rank", "title": "서울 신고가 순위"}]
    assert order(log)[:2] == ["c02", "c03"]


def test_morning_and_evening_pick_different_gus_on_the_same_day():
    log = [entry(c, f"2026-10-0{i + 1}T10:11") for i, c in enumerate(CODES[:5])]
    morning = order(log)[0]
    log.append(entry(morning, "2026-10-20T10:11"))
    evening = order(log)[0]
    assert morning == "c05" and evening == "c06"


def test_reel_caption_first_line_differs_from_map_card():
    meta = {"top": [("역삼동", "래미안", 250000, 34)]}
    import datetime as dt
    d = dt.date(2026, 10, 22)
    card = post.dong_caption("강남구", "30평대", meta, d).splitlines()[0]
    reel = post.dong_caption("강남구", "30평대", meta, d, reel_=True).splitlines()[0]
    assert card != reel and not reel.startswith(card.split(" 🗺️")[0] + " ")
