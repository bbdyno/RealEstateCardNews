"""collector/sigungu.json 을 만든다(한 번만 돌리면 된다).

PublicDataReader 에 들어 있는 법정동 코드(2022-09 기준)에서 살아 있는 시군구만 뽑고, 그 뒤 바뀐 행정구역을 보정한다.
국토부 실거래 API 는 행정구역이 바뀐 지역을 옛 코드로 돌려주는 경우가 있어서, 바뀐 곳은 옛 코드와 새 코드를 함께
조회 목록(query)에 넣고 수집 단계에서 중복을 없앤다.

  - 강원도 42 → 강원특별자치도 51 (2023-06-11)
  - 전라북도 45 → 전북특별자치도 52 (2024-01-18)
  - 경북 군위군 47720 → 대구 군위군 27720 (2023-07-01)
  - 2026 개편(전남광주통합특별시, 인천 제물포·영종·서해·검단구, 부천·화성 구 신설)은 국토부가 새 코드로만 준다.
    옛 코드는 전 기간 0건이라 빼고 REORG_ADD 의 새 코드로 바꾼다(2026-09-30 실제 조회로 확인).

사용: .venv/bin/python scripts/make_sigungu.py <code_bdong.json 경로>
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "collector" / "sigungu.json"

# 새 시도 이름·코드
RENAMED_SIDO = {"42": ("51", "강원특별자치도"), "45": ("52", "전북특별자치도")}
MOVED = {"47720": ("27720", "대구광역시", "군위군")}

# 2026 개편 지역: 국토부가 새 코드로만 준다(옛 코드는 전 기간 0건). 2026-09-30 scripts/verify_codes.py 로
# 코드마다 실제 거래를 받아 동 이름으로 확인했다. 옛 코드는 목록에서 빼고 아래로 바꾼다.
REORG_DROP_PREFIX = ("29", "46")                  # 광주광역시 · 전라남도 → 전남광주통합특별시
REORG_DROP = {"28110", "28140", "28260",          # 인천 중·동·서구 → 제물포·영종·서해·검단구
              "41190", "41590"}                   # 부천시 · 화성시 → 구 신설
JG = "전남광주통합특별시"
REORG_ADD = [
    *[(c, JG, n, "도") for c, n in [("12110", "목포시"), ("12130", "여수시"), ("12150", "순천시"), ("12170", "나주시"),
                                    ("12190", "광양시")]],
    *[(c, JG, n, "광역시") for c, n in [("12210", "광주 동구"), ("12240", "광주 서구"), ("12270", "광주 남구"),
                                       ("12300", "광주 북구"), ("12330", "광주 광산구")]],
    *[(f"12{710 + 10 * i}", JG, n, "도") for i, n in enumerate(
        ["담양군", "곡성군", "구례군", "고흥군", "보성군", "화순군", "장흥군", "강진군", "해남군", "영암군", "무안군",
         "함평군", "영광군", "장성군", "완도군", "진도군", "신안군"])],
    ("28125", "인천광역시", "제물포구", "수도권"), ("28155", "인천광역시", "영종구", "수도권"),
    ("28275", "인천광역시", "서해구", "수도권"), ("28290", "인천광역시", "검단구", "수도권"),
    ("41192", "경기도", "부천시 원미구", "수도권"), ("41194", "경기도", "부천시 소사구", "수도권"),
    ("41196", "경기도", "부천시 오정구", "수도권"),
    ("41591", "경기도", "화성시 만세구", "수도권"), ("41593", "경기도", "화성시 효행구", "수도권"),
    ("41595", "경기도", "화성시 병점구", "수도권"), ("41597", "경기도", "화성시 동탄구", "수도권"),
]

# 권역 — 수도권은 자세히, 광역시·세종은 시 단위, 도는 주요 도시(콘텐츠 기준. 웹은 전부 만든다)
GROUP = {"11": "수도권", "41": "수도권", "28": "수도권",
         "26": "광역시", "27": "광역시", "29": "광역시", "30": "광역시", "31": "광역시", "36": "광역시"}
SIDO_SHORT = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주",
              "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
              "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남", "전북특별자치도": "전북",
              "전라남도": "전남", "전남광주통합특별시": "전남광주", "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주"}


def blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or str(v).strip() == ""


def main(src: str) -> None:
    d = json.load(open(src, encoding="utf-8"))
    cols = list(d)
    rows = [{c: d[c][k] for c in cols} for k in d[cols[0]]]
    live = [r for r in rows if blank(r["말소일자"])]
    names: dict[str, tuple[str, str]] = {}
    for r in live:
        code = str(r["시군구코드"])
        if code.endswith("000"):
            continue
        # 세종처럼 시군구가 없는 시도는 시군구명이 비어 있다
        name = "세종시" if blank(r["시군구명"]) and code == "36110" else str(r["시군구명"]).strip()
        # 출장소(예: 28265 서구검단출장)는 실거래 조회 단위가 아니다. 이름이 잘려 '…출' 로 끝나기도 한다
        if blank(name) or name == "nan" or "출장" in name or name.endswith("출"):
            continue
        names[code] = (r["시도명"], name)
    # 구가 있는 시(예: 수원시 41110 → 수원시 장안구 41111…)는 부모를 빼고 구만 남긴다 — 국토부는 구 코드로 준다.
    # 코드 끝자리로 가르면 영동군 43740 / 증평군 43745 같은 이웃을 부모·자식으로 착각하므로 이름으로 가른다.
    parents = {c for c, (_, n) in names.items()
               if any(o != c and on.startswith(n + " ") for o, (_, on) in names.items())}
    out = []
    for code, (sido, name) in sorted(names.items()):
        if code in parents:
            continue
        query = [code]
        sido_code = code[:2]
        if code in MOVED:
            new, sido, name = MOVED[code]
            query, code = [new, code], new
        elif sido_code in RENAMED_SIDO:
            new_sido, sido = RENAMED_SIDO[sido_code]
            new = new_sido + code[2:]
            query, code = [new, code], new
        short = SIDO_SHORT.get(sido, sido)
        out.append({"code": code, "sido": sido, "sido_short": short, "name": name,
                    "group": GROUP.get(code[:2], "도"), "query": query})
    out = [r for r in out if not r["code"].startswith(REORG_DROP_PREFIX) and r["code"] not in REORG_DROP]
    for code, sido, name, group in REORG_ADD:
        out.append({"code": code, "sido": sido, "sido_short": SIDO_SHORT.get(sido, sido), "name": name,
                    "group": group, "query": [code]})
    out.sort(key=lambda r: r["code"])
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    by = {}
    for r in out:
        by.setdefault(r["sido_short"], 0)
        by[r["sido_short"]] += 1
    print(f"{len(out)}개 시군구 → {OUT}")
    print(by)


if __name__ == "__main__":
    main(sys.argv[1])
