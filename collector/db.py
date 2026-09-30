"""SQLite 저장소. 거래는 종류와 상관없이 한 테이블(deals)에 모은다."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "realestate.db"
SIGUNGU = Path(__file__).with_name("sigungu.json")

SCHEMA = """
CREATE TABLE IF NOT EXISTS deals(
  uid TEXT PRIMARY KEY,
  kind TEXT NOT NULL,          -- apt 아파트 / offi 오피스텔 / rh 연립·다세대 / sh 단독·다가구 / silv 분양권·입주권
  trade TEXT NOT NULL,         -- sale 매매 / rent 전월세
  sgg TEXT NOT NULL,           -- 대표 시군구 코드(collector/sigungu.json 의 code)
  umd TEXT, jibun TEXT, name TEXT, apt_seq TEXT,
  area REAL,                   -- 전용면적㎡ (단독·다가구는 연면적)
  land_area REAL,              -- 대지권면적㎡(연립·다세대) / 대지면적㎡(단독·다가구)
  floor INTEGER, build_year INTEGER,
  ymd TEXT NOT NULL,           -- 계약일
  price INTEGER,               -- 매매가(만원)
  deposit INTEGER, rent INTEGER,  -- 보증금·월세(만원)
  contract TEXT, house_type TEXT,
  cancelled INTEGER NOT NULL DEFAULT 0,
  direct INTEGER NOT NULL DEFAULT 0,
  demo INTEGER NOT NULL DEFAULT 0,   -- 1 이면 개발용 가짜 데이터. 사이트는 샘플 표시를 붙인다
  fetched_at REAL
);
CREATE INDEX IF NOT EXISTS deals_main ON deals(kind, trade, sgg, ymd);
CREATE INDEX IF NOT EXISTS deals_cx ON deals(kind, sgg, umd, jibun, name);
CREATE INDEX IF NOT EXISTS deals_seq ON deals(apt_seq);
CREATE TABLE IF NOT EXISTS fetch_log(
  kind TEXT, lawd TEXT, ym TEXT, rows INTEGER, at REAL,
  PRIMARY KEY(kind, lawd, ym)
);
CREATE TABLE IF NOT EXISTS api_calls(day TEXT, kind TEXT, n INTEGER, PRIMARY KEY(day, kind));
CREATE TABLE IF NOT EXISTS redevelop(
  id TEXT PRIMARY KEY,         -- 출처+구역명으로 만든 키
  sido TEXT, sgg TEXT, sgg_name TEXT, umd TEXT,
  zone TEXT NOT NULL,          -- 구역명
  biz TEXT,                    -- 재개발 / 재건축 / 도시환경 / 소규모·모아타운 / 공공재개발 …
  stage TEXT,                  -- 추진 단계(정비구역지정·추진위·조합설립·사업시행인가·관리처분·착공·준공 …)
  stage_no INTEGER,            -- 단계 순서(0~8). 모르면 NULL
  area REAL, households INTEGER, address TEXT,
  source TEXT, source_date TEXT,
  demo INTEGER NOT NULL DEFAULT 0
);
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    return c


def regions() -> list[dict]:
    return json.loads(SIGUNGU.read_text(encoding="utf-8"))


COLS = ("uid", "kind", "trade", "sgg", "umd", "jibun", "name", "apt_seq", "area", "land_area", "floor", "build_year",
        "ymd", "price", "deposit", "rent", "contract", "house_type", "cancelled", "direct", "demo", "fetched_at")


def upsert(c: sqlite3.Connection, recs: list[dict], demo: int = 0) -> int:
    now = time.time()
    rows = [tuple({**r, "demo": demo, "fetched_at": now}.get(k) for k in COLS) for r in recs]
    c.executemany(
        f"INSERT INTO deals({','.join(COLS)}) VALUES({','.join('?' * len(COLS))}) "
        "ON CONFLICT(uid) DO UPDATE SET cancelled=excluded.cancelled, fetched_at=excluded.fetched_at", rows)
    return len(rows)


def logged(c: sqlite3.Connection, kind: str, lawd: str, ym: str) -> bool:
    return c.execute("SELECT 1 FROM fetch_log WHERE kind=? AND lawd=? AND ym=?", (kind, lawd, ym)).fetchone() is not None


def log_fetch(c: sqlite3.Connection, kind: str, lawd: str, ym: str, rows: int) -> None:
    c.execute("INSERT OR REPLACE INTO fetch_log VALUES(?,?,?,?,?)", (kind, lawd, ym, rows, time.time()))


def today() -> str:
    return dt.date.today().isoformat()


def calls_today(c: sqlite3.Connection, kind: str) -> int:
    r = c.execute("SELECT n FROM api_calls WHERE day=? AND kind=?", (today(), kind)).fetchone()
    return r["n"] if r else 0


def add_calls(c: sqlite3.Connection, kind: str, n: int) -> None:
    c.execute("INSERT INTO api_calls VALUES(?,?,?) ON CONFLICT(day,kind) DO UPDATE SET n=n+excluded.n", (today(), kind, n))


def has_demo(c: sqlite3.Connection) -> bool:
    return bool(c.execute("SELECT 1 FROM deals WHERE demo=1 LIMIT 1").fetchone()
                or c.execute("SELECT 1 FROM redevelop WHERE demo=1 LIMIT 1").fetchone())
