import datetime as dt

from cards import post


def test_evening_reel_is_always_motion(monkeypatch):
    called = []
    monkeypatch.setattr(post, "make_motion", lambda *a, **k: called.append(("motion", k.get("fmt"))) or "m")
    monkeypatch.setattr(post, "make_dong_reel", lambda *a, **k: called.append(("dong", None)) or "d")
    for d in range(7):
        assert post.reel_of_day(dt.date(2026, 10, 19) + dt.timedelta(days=d), [], []) == "m"
    assert all(kind == "motion" for kind, _ in called)
