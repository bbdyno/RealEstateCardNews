"""표 칸 폭 점검: 나올 수 있는 가장 긴 값(가격 99.99 · 날짜 12.31 · 퍼센트 −44.4% 등)으로 표를 찍어 잘리는 칸이 없는지 본다.
실제 데이터로는 그날 나온 값만 확인되니(10월 날짜 '10.01' 이 서버에서만 잘렸다), 칸 폭을 바꾸면 이걸 돌린다.

  .venv/bin/python -m scripts.check_widths
"""
import datetime as dt
import sys
import tempfile
from pathlib import Path

from cards import rank
from cards.budget import env, shoot
from collector import db
from web.build import I3D

LONG = dict(gu="화성시 동탄구", name="초롱꽃마을12단지e편한세상운정어반프라임", umd="반포동", age=99, py=99, price=999900, prev=999900, hi=999900,
            up=-0.444, vs_hi=-0.444, ymd="2026-12-31", n3=999, n3y=999, ppp=29999, bar=-1.0, gu_one="수원시 영통구", is_high=True)


def main() -> int:
    today = dt.date(2026, 12, 31)
    bad = 0
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        base = dict(today=today, I3D=I3D, logo=(db.ROOT / "web" / "static" / "logo.svg").as_uri(), total=9, no=2, n=40, n_shown=20,
                    title="서울 99억대", badge="30평형", chips=["최근 3개월", "12.31 신고분까지", "해제·직거래 제외"])
        rows = [dict(LONG, rank=i, up=(-0.444 if i % 2 else 0.444)) for i in range(1, 21)]
        jobs = [("budget_table", dict(base, page=[dict(r, gu=f"화성시 동탄구") for r in rows]))]
        for fmt in rank.FORMATS:
            page = [dict(r, n3=9999) for r in rows] if fmt == "gu" else rows      # 시·구는 3개월 거래가 네 자리까지
            jobs.append(("rank_table", dict(base, page=page, fmt=fmt, f=rank.FORMATS[fmt], cols=rank.COLS[fmt], sido="서울")))
        for tpl, ctx in jobs:
            (out / tpl).mkdir(exist_ok=True)
            _, over = shoot(env(), [(tpl, {})], ctx, out / tpl)
            n = sum(over.values())
            print(f"{tpl} {ctx.get('fmt', '')}: 넘침 {n}")
            bad += n
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
