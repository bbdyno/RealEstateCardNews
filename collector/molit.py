"""국토교통부 실거래가 공개 API(공공데이터포털) 클라이언트.

한 번 호출 = (자료 종류, 시군구 코드 LAWD_CD, 계약 연월 DEAL_YMD). 응답은 XML 이다.
금액은 '만원' 단위 문자열(쉼표 포함)이고, 해제된 거래는 cdealType='O' 로 표시된다.
엔드포인트·필드 이름은 PublicDataReader(1.1.1)와 공공데이터포털 문서를 따른다.
"""
from __future__ import annotations

import asyncio
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass

import httpx

BASE = "https://apis.data.go.kr/1613000"

# 종류 → (서비스, 오퍼레이션). kind 는 '유형_거래' (apt/offi/rh/sh/silv × sale/rent)
KINDS: dict[str, tuple[str, str]] = {
    "apt_sale": ("RTMSDataSvcAptTradeDev", "getRTMSDataSvcAptTradeDev"),
    "apt_rent": ("RTMSDataSvcAptRent", "getRTMSDataSvcAptRent"),
    "silv_sale": ("RTMSDataSvcSilvTrade", "getRTMSDataSvcSilvTrade"),    # 분양권·입주권 전매
    "offi_sale": ("RTMSDataSvcOffiTrade", "getRTMSDataSvcOffiTrade"),
    "offi_rent": ("RTMSDataSvcOffiRent", "getRTMSDataSvcOffiRent"),
    "rh_sale": ("RTMSDataSvcRHTrade", "getRTMSDataSvcRHTrade"),          # 연립·다세대(빌라)
    "rh_rent": ("RTMSDataSvcRHRent", "getRTMSDataSvcRHRent"),
    "sh_sale": ("RTMSDataSvcSHTrade", "getRTMSDataSvcSHTrade"),          # 단독·다가구
}
PAGE = 1000


class ApiError(RuntimeError):
    pass


class QuotaExceeded(ApiError):
    """그날 호출 한도를 다 썼다 — 이 종류는 내일 이어서 한다."""


class KeyProblem(ApiError):
    """키가 없거나, 등록 전이거나, 이 API 에 활용 신청을 하지 않았다."""


@dataclass
class Page:
    items: list[dict]
    total: int


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def parse(xml: str) -> Page:
    """응답 XML → 항목(dict: 필드명 → 문자열)과 전체 건수. 오류 응답은 알맞은 예외로 바꾼다."""
    body = xml.strip()
    if not body.startswith("<"):
        # 게이트웨이가 평문으로 답하는 경우(예: "API rate limit exceeded", "Unauthorized")
        low = body.lower()
        if "limit" in low:
            raise QuotaExceeded(body[:200])
        if "unauthorized" in low or "forbidden" in low:
            raise KeyProblem(body[:200])
        raise ApiError(body[:200])
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:                       # 점검 안내 HTML 등
        raise ApiError(f"XML 아님: {body[:120]}") from e
    if root.tag == "OpenAPI_ServiceResponse":
        hdr = root.find("cmmMsgHeader")
        code = _text(hdr.find("returnReasonCode")) if hdr is not None else ""
        err = _text(hdr.find("errMsg")) if hdr is not None else ""          # 예: SERVICE_KEY_IS_NOT_REGISTERED_ERROR
        auth = _text(hdr.find("returnAuthMsg")) if hdr is not None else ""  # 예: 등록되지 않은 서비스키
        msg = " / ".join(x for x in (auth, err) if x)
        if code == "22" or "LIMITED_NUMBER" in err:
            raise QuotaExceeded(f"{code} {msg}")
        if code in ("20", "30", "31", "32", "33") or "SERVICE_KEY" in err or "ACCESS_DENIED" in err:
            raise KeyProblem(f"{code} {msg}")
        raise ApiError(f"{code} {msg}")
    result = _text(root.find("header/resultCode"))
    if result not in ("000", "00"):
        raise ApiError(f"{result} {_text(root.find('header/resultMsg'))}")
    items = [{c.tag: (c.text or "").strip() for c in it} for it in root.findall("body/items/item")]
    total = int(_text(root.find("body/totalCount")) or len(items))
    return Page(items, total)


class Client:
    def __init__(self, key: str, *, concurrency: int = 4, timeout: float = 30):
        if not key:
            raise KeyProblem(".env 의 DATA_GO_KR_KEY 가 비어 있습니다.")
        # 포털은 인코딩 키(%2B…)와 디코딩 키 두 가지를 준다. 어느 쪽을 넣어도 되도록 풀어 두고, 요청할 때 한 번만 인코딩한다
        self.key = urllib.parse.unquote(key)
        self.sem = asyncio.Semaphore(concurrency)
        self.http = httpx.AsyncClient(timeout=timeout)
        self.calls: Counter = Counter()   # 종류별 호출 수(한도가 종류마다 따로다)

    async def close(self) -> None:
        await self.http.aclose()

    async def _get(self, kind: str, lawd: str, ym: str, page: int) -> Page:
        svc, op = KINDS[kind]
        params = {"serviceKey": self.key, "LAWD_CD": lawd, "DEAL_YMD": ym, "pageNo": page, "numOfRows": PAGE}
        last: Exception | None = None
        for attempt in range(4):
            async with self.sem:
                self.calls[kind] += 1
                try:
                    r = await self.http.get(f"{BASE}/{svc}/{op}", params=params)
                except httpx.HTTPError as e:     # 네트워크가 끊겼다 — 잠깐 쉬고 다시
                    last = e
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
            if r.status_code == 429:
                raise QuotaExceeded("HTTP 429")
            if r.status_code in (401, 403):
                parse(r.text)          # 본문(XML)에 사유가 있다 — 알맞은 예외로 바뀐다
                raise KeyProblem(f"HTTP {r.status_code}")
            if r.status_code >= 500:
                last = ApiError(f"HTTP {r.status_code}")
                await asyncio.sleep(2 * (attempt + 1))
                continue
            return parse(r.text)
        raise ApiError(f"{kind} {lawd} {ym}: {last}")

    async def fetch(self, kind: str, lawd: str, ym: str) -> list[dict]:
        """한 달·한 시군구 전부(여러 쪽이면 이어 받는다)."""
        first = await self._get(kind, lawd, ym, 1)
        items = list(first.items)
        pages = -(-first.total // PAGE)
        for p in range(2, pages + 1):
            items += (await self._get(kind, lawd, ym, p)).items
        return items
