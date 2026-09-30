"""실거래 수집. 매일 같은 명령 하나로 돈다.

  .venv/bin/python -m collector.collect            # 최근 36개월 중 빠진 달을 채우고, 최근 3개월은 다시 받는다
  .venv/bin/python -m collector.collect --plan     # 호출 없이 할 일만 센다
  .venv/bin/python -m collector.collect --only 서울 --kinds apt_sale,apt_rent --months 12

- 지난달까지 받아 둔 달은 다시 받지 않는다. 최근 N개월(기본 3)은 신고 기한(30일)과 해제·정정 때문에 매일 다시 받는다.
- 호출 한도는 API(종류)마다 따로다(개발계정 하루 1만). 종류마다 --budget 까지만 쓰고, 한도에 걸리면 그 종류만 멈춘다.
  남은 달은 다음 날 이어서 채운다 — 최근 달·수도권부터 채우므로 중간에 멈춰도 가장 쓸모 있는 데이터가 먼저 쌓인다.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
import os

from dotenv import load_dotenv

from . import db
from .molit import KINDS, ApiError, Client, KeyProblem, QuotaExceeded
from .normalize import record, with_uids

log = logging.getLogger("collect")
GROUP_ORDER = {"수도권": 0, "광역시": 1, "도": 2}


def months_back(n: int, today: dt.date | None = None) -> list[str]:
    """이번 달부터 거꾸로 n 개월(YYYYMM)."""
    d = (today or dt.date.today()).replace(day=1)
    out = []
    for _ in range(n):
        out.append(d.strftime("%Y%m"))
        d = (d - dt.timedelta(days=1)).replace(day=1)
    return out


def pick_regions(only: str | None) -> list[dict]:
    rs = db.regions()
    if only:
        keys = {k.strip() for k in only.split(",")}
        rs = [r for r in rs if r["code"] in keys or r["sido_short"] in keys or r["sido"] in keys or r["name"] in keys]
    return sorted(rs, key=lambda r: (GROUP_ORDER.get(r["group"], 9), r["code"]))


def plan(c, kinds: list[str], regions: list[dict], months: list[str], recent: int) -> dict[str, list[tuple]]:
    """종류별 작업 목록 — (대표코드, 조회코드들, 연월). 최근 달·수도권이 앞."""
    fresh = set(months[:recent])
    todo: dict[str, list[tuple]] = {k: [] for k in kinds}
    for ym in months:
        for r in regions:
            for k in kinds:
                if ym in fresh or not db.logged(c, k, r["code"], ym):
                    todo[k].append((r["code"], r["query"], ym))
    return todo


async def run_kind(client: Client, c, kind: str, jobs: list[tuple], budget: int) -> dict:
    stat = {"kind": kind, "jobs": 0, "rows": 0, "errors": 0, "stopped": None}
    for sgg, query, ym in jobs:
        used = db.calls_today(c, kind)
        if used + len(query) > budget:
            stat["stopped"] = f"오늘 예산 {budget}회 소진"
            break
        before = client.calls[kind]
        try:
            # 옛 코드·새 코드로 같은 거래를 두 번 받을 수 있다. 중복 키는 응답마다 따로 매기고(한 응답 안의 같은 값 두 건은
            # 실제 두 건) 응답끼리는 같은 키를 하나로 합친다 — 합친 뒤 매기면 같은 거래가 두 건으로 세어진다.
            by_uid: dict[str, dict] = {}
            for lawd in query:
                items = await client.fetch(kind, lawd, ym)
                for rec in with_uids([r for r in (record(kind, it, sgg) for it in items) if r]):
                    by_uid[rec["uid"]] = rec
        except QuotaExceeded as e:
            stat["stopped"] = f"호출 한도: {e}"
            break
        except ApiError as e:                       # 이 달·이 지역만 건너뛴다. 기록을 남기지 않으니 다음 실행에서 다시 받는다
            stat["errors"] += 1
            log.warning("건너뜀 %s %s %s: %s", kind, sgg, ym, e)
            continue
        finally:
            db.add_calls(c, kind, client.calls[kind] - before)
        recs = list(by_uid.values())
        db.upsert(c, recs)
        db.log_fetch(c, kind, sgg, ym, len(recs))
        c.commit()
        stat["jobs"] += 1
        stat["rows"] += len(recs)
        if stat["jobs"] % 50 == 0:
            log.info("%s %d/%d (행 %d)", kind, stat["jobs"], len(jobs), stat["rows"])
    return stat


async def main_async(a) -> None:
    load_dotenv(db.ROOT / ".env")
    kinds = [k.strip() for k in a.kinds.split(",")] if a.kinds else list(KINDS)
    regions = pick_regions(a.only)
    months = months_back(a.months)
    c = db.connect()
    todo = plan(c, kinds, regions, months, a.recent)
    total = {k: sum(len(q) for _, q, _ in v) for k, v in todo.items()}
    log.info("대상 시군구 %d · %d개월 · 종류 %d → 예상 호출(1쪽 기준) %s", len(regions), len(months), len(kinds), total)
    if a.plan:
        return
    hint = "→ 공공데이터포털에서 이 API 에 활용 신청했는지, 일반 인증키(Decoding)가 .env 의 DATA_GO_KR_KEY 에 들어 있는지 확인하세요."
    try:
        client = Client(os.environ.get("DATA_GO_KR_KEY", "").strip(), concurrency=a.concurrency)
    except KeyProblem as e:
        raise SystemExit(f"인증키 문제: {e}\n{hint}")
    try:
        # 종류마다 한도가 따로라 종류끼리는 동시에 돈다
        stats = await asyncio.gather(*(run_kind(client, c, k, todo[k], a.budget) for k in kinds))
    except KeyProblem as e:
        raise SystemExit(f"인증키 문제: {e}\n{hint}")
    finally:
        await client.close()
    for s in stats:
        log.info("%-9s 작업 %5d · 행 %7d · 건너뜀 %d%s", s["kind"], s["jobs"], s["rows"], s["errors"],
                 f" · 멈춤: {s['stopped']}" if s["stopped"] else "")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--months", type=int, default=36)
    p.add_argument("--recent", type=int, default=3, help="매일 다시 받는 최근 개월 수")
    p.add_argument("--kinds", help="쉼표로 구분: " + ",".join(KINDS))
    p.add_argument("--only", help="시도 약칭·시도명·시군구명·코드(쉼표 구분)")
    p.add_argument("--budget", type=int, default=9500, help="종류마다 하루에 쓸 최대 호출 수")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--plan", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)    # 요청 URL 에 인증키가 들어간다 — 로그에 남기지 않는다
    asyncio.run(main_async(a))


if __name__ == "__main__":
    main()
