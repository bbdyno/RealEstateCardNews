"""API 항목(종류마다 필드가 다르다) → 한 가지 거래 레코드."""
from __future__ import annotations

import hashlib
from collections import Counter


def _int(v: str | None) -> int | None:
    v = (v or "").replace(",", "").strip()
    try:
        return int(float(v)) if v else None
    except ValueError:
        return None


def _float(v: str | None) -> float | None:
    v = (v or "").replace(",", "").strip()
    try:
        return float(v) if v else None
    except ValueError:
        return None


NAME_FIELD = {"apt": "aptNm", "silv": "aptNm", "offi": "offiNm", "rh": "mhouseNm", "sh": None}


def record(kind: str, it: dict, sgg: str) -> dict | None:
    """kind 는 'apt_sale' 같은 이름. sgg 는 우리 쪽 대표 시군구 코드(옛 코드로 받은 것도 새 코드로 모은다)."""
    typ, trade = kind.split("_")
    y, m, d = _int(it.get("dealYear")), _int(it.get("dealMonth")), _int(it.get("dealDay"))
    if not (y and m and d):
        return None
    nf = NAME_FIELD[typ]
    name = (it.get(nf) or "").strip() if nf else ""
    area = _float(it.get("excluUseAr")) if typ != "sh" else _float(it.get("totalFloorAr"))
    land = _float(it.get("landAr")) if typ == "rh" else (_float(it.get("plottageAr")) if typ == "sh" else None)
    house_type = (it.get("houseType") or it.get("ownershipGbn") or "").strip() or None
    rec = {
        "kind": typ, "trade": trade, "sgg": sgg,
        "umd": (it.get("umdNm") or "").strip(),
        "jibun": (it.get("jibun") or "").strip(),
        "name": name,
        "apt_seq": (it.get("aptSeq") or "").strip() or None,
        "area": area, "land_area": land,
        "floor": _int(it.get("floor")),
        "build_year": _int(it.get("buildYear")),
        "ymd": f"{y:04d}-{m:02d}-{d:02d}",
        "price": _int(it.get("dealAmount")) if trade == "sale" else None,
        "deposit": _int(it.get("deposit")) if trade == "rent" else None,
        "rent": _int(it.get("monthlyRent")) if trade == "rent" else None,
        "contract": (it.get("contractType") or "").strip() or None,
        "house_type": house_type,
        "cancelled": 1 if (it.get("cdealType") or "").strip().upper() == "O" else 0,
        "direct": 1 if "직거래" in (it.get("dealingGbn") or "") else 0,
    }
    return rec


def with_uids(recs: list[dict]) -> list[dict]:
    """중복 제거 키. 같은 날 같은 값의 거래가 실제로 두 건일 수 있으므로, 같은 키가 한 응답에 몇 번째로 나왔는지를 붙인다.
    옛 코드·새 코드로 같은 거래를 두 번 받아도 순번이 같게 나오므로 하나로 합쳐진다. 해제 여부는 키에 넣지 않는다(나중에 바뀐다)."""
    seen: Counter = Counter()
    for r in recs:
        base = "|".join(str(r[k]) for k in ("kind", "trade", "sgg", "umd", "jibun", "name", "area", "land_area",
                                            "floor", "ymd", "price", "deposit", "rent"))
        seen[base] += 1
        r["uid"] = hashlib.sha1(f"{base}#{seen[base]}".encode()).hexdigest()[:20]
    return recs
