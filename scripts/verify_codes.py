"""행정구역 개편으로 새로 생긴 시군구 코드를 실제 API 로 확인한다(하루 한도가 남아 있을 때 한 번).

2026 년 현재 국토부 실거래 API 는 개편된 지역을 새 코드로만 준다(옛 코드는 전 기간 0건):
  - 전남광주통합특별시(시도 12): 옛 광주 29xxx 5개 구 + 전남 46xxx 22개 시군
  - 인천 제물포·영종·서해·검단구(옛 중·동·서구)
  - 부천 원미·소사·오정구, 화성 만세·효행·병점·동탄구
후보 코드마다 2026-08 단독·다가구(없으면 오피스텔) 매매를 한 번 조회하고, 나온 동 이름을 2022 법정동 목록과 맞춰
옛 시군구를 알아낸다. 결과는 data/code_probe.json 에 전부 남긴다(도중에 한도에 걸려도 받은 만큼은 남는다).

  .venv/bin/python scripts/verify_codes.py
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

from collector.molit import Client, QuotaExceeded  # noqa: E402

BDONG = ROOT / ".venv/lib/python3.14/site-packages/PublicDataReader/raw/code_bdong.json"
OUT = ROOT / "data" / "code_probe.json"
CANDIDATES = ([f"12{n:03d}" for n in range(100, 1000, 10)]
              + [f"28{n:03d}" for n in range(100, 300, 5)]
              + [f"4119{n}" for n in range(1, 10)] + [f"4159{n}" for n in range(1, 10)])


def old_umds() -> dict[str, tuple[str, str, set]]:
    d = json.load(open(BDONG, encoding="utf-8"))
    cols = list(d)
    blank = lambda v: v is None or (isinstance(v, float) and math.isnan(v))
    out: dict[str, tuple[str, str, set]] = {}
    for k in d[cols[0]]:
        r = {c: d[c][k] for c in cols}
        if blank(r["말소일자"]) or blank(r["읍면동명"]):
            continue
        code = str(r["시군구코드"])
        if code[:2] in ("29", "46", "28", "41"):
            out.setdefault(code, (r["시도명"], str(r["시군구명"]), set()))[2].add(r["읍면동명"])
    return out


async def main() -> None:
    load_dotenv(ROOT / ".env")
    olds = old_umds()
    done = json.loads(OUT.read_text()) if OUT.exists() else {}
    client = Client(os.environ["DATA_GO_KR_KEY"], concurrency=2)
    try:
        for code in CANDIDATES:
            if code in done and done[code].get("n", -1) >= 0:
                continue
            items: list[dict] = []
            used = None
            try:
                for kind in ("sh_sale", "offi_sale", "rh_sale"):
                    items = await client.fetch(kind, code, "202608")
                    used = kind
                    if items:
                        break
            except QuotaExceeded as e:
                print(f"한도에 걸려 멈춤({code}): {e}")
                break
            umds = Counter(it.get("umdNm", "").strip() for it in items)
            match = sorted(((len(set(umds) & u), old, sd, nm) for old, (sd, nm, u) in olds.items()), reverse=True)[:2]
            done[code] = {"n": len(items), "kind": used, "umds": dict(umds.most_common(8)),
                          "old": [m[1:] for m in match if m[0]]}
            OUT.write_text(json.dumps(done, ensure_ascii=False, indent=1))
            if items:
                print(code, len(items), "→", done[code]["old"][:1], list(umds)[:3])
    finally:
        await client.close()
    print(f"기록: {OUT} · 호출 {dict(client.calls)}")


if __name__ == "__main__":
    asyncio.run(main())
