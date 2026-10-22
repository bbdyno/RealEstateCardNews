"""모션 릴스(reels/build.py)의 시각 계획·배경음 설계·검수 판정 — DB·엔진 없이 도는 부분만."""
from reels import build


def test_plan_bars():
    c = build.plan(5)
    assert c["intro"] == 0 and c["r5"] == 2.4 and c["r2"] == 9.6
    assert c["r1"] == 12.0 and c["outro"] == 16.8 and c["end"] == 19.2   # 1위는 두 마디, 앞뒤 한 마디


def test_plan_three_rows():
    c = build.plan(3)
    assert [c["r3"], c["r2"], c["r1"], c["outro"], c["end"]] == [2.4, 4.8, 7.2, 12.0, 14.4]


def test_music_events_inside_video():
    c = build.plan(5)
    spec = build.music_spec(c, 5)
    assert spec["duration"] == c["end"]
    assert all(0 <= e["t"] < c["end"] for e in spec["events"])
    assert any(e["type"] == "boom" and e["t"] == c["r1"] for e in spec["events"])   # 1위 착지에 맞춘다


def test_verdict_picks_only_failures(tmp_path):
    rep = tmp_path / "qa_report.md"
    rep.write_text("# 자동 검수\n\n## 고칠 것\n- [ ] 멈춘 화면 20%\n- [x] 고친 것\n\n## 사람이 볼 것\n- [ ] 소리 들어 보기\n", encoding="utf-8")
    out = build.verdict("✓ 움직임 기준 통과\n△ 1.0~2.0s 동안 1.0초 멈춤\n", rep)
    assert out == ["△ 1.0~2.0s 동안 1.0초 멈춤", "멈춘 화면 20%"]          # '사람이 볼 것'은 실패로 치지 않는다


def test_verdict_clean(tmp_path):
    rep = tmp_path / "qa_report.md"
    rep.write_text("# 자동 검수\n\n## 사람이 볼 것\n- [ ] 소리 들어 보기\n", encoding="utf-8")
    assert build.verdict("✓ 움직임 기준 통과\n✓ 섬광 3회\n", rep) == []
