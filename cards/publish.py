"""인스타 게시·이미지 호스팅·텔레그램 알림. 카드뉴스 봇(PoliticsCardNews/cardnews/publish)의 방식을 동기 코드로 옮겼다.

- 이미지: 이 저장소의 'media' 브랜치에 올려 raw.githubusercontent.com 주소를 쓴다(인스타는 공개 주소의 JPEG 만 받는다).
- 인스타: Instagram Login 방식(graph.instagram.com). 환경변수 IG_USER_ID · IG_ACCESS_TOKEN.
- 텔레그램: 환경변수 TELEGRAM_BOT_TOKEN · TELEGRAM_CHAT_ID. 없으면 알림을 건너뛴다.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

API = "https://graph.instagram.com/v23.0"
REPO = os.environ.get("GITHUB_REPOSITORY", "bbdyno/RealEstateCardNews")
KEEP_DAYS = 14               # media 브랜치에 남겨 둘 기간(인스타가 이미지를 가져간 뒤에는 필요 없다)


class PublishError(RuntimeError):
    pass


# ── 이미지 호스팅 ────────────────────────────────────────────────────────────

def _git(*args, cwd=None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def upload(paths: list[Path], slug: str) -> list[str]:
    """JPEG 들을 media 브랜치 media/<날짜-slug>/ 에 올리고 커밋 고정 주소를 돌려준다. 오래된 폴더는 지운다."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    remote = f"https://x-access-token:{token}@github.com/{REPO}.git" if token else f"https://github.com/{REPO}.git"
    with tempfile.TemporaryDirectory() as d:
        wd = Path(d) / "media"
        try:
            _git("clone", "--depth", "1", "--branch", "media", remote, str(wd))
        except subprocess.CalledProcessError:                  # 처음이면 빈 브랜치를 만든다
            wd.mkdir()
            _git("init", "-b", "media", cwd=wd)
            _git("remote", "add", "origin", remote, cwd=wd)
        _git("config", "user.name", "github-actions[bot]", cwd=wd)
        _git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com", cwd=wd)
        root = wd / "media"
        root.mkdir(exist_ok=True)
        cutoff = (dt.date.today() - dt.timedelta(days=KEEP_DAYS)).strftime("%Y%m%d")
        for old in root.iterdir():
            if old.is_dir() and old.name[:8] < cutoff:
                shutil.rmtree(old)
        # 인스타 서버는 주소에 한글이 있으면 이미지를 못 가져온다(400 · 2207052) — 영문·숫자만 남긴다
        slug = re.sub(r"[^A-Za-z0-9-]+", "", slug).strip("-") or "card"
        folder = root / f"{dt.date.today():%Y%m%d}-{slug}-{int(time.time())}"
        folder.mkdir()
        for p in paths:
            shutil.copy2(p, folder / p.name)
        _git("add", "-A", cwd=wd)
        _git("commit", "-q", "-m", f"카드 이미지 {folder.name}", cwd=wd)
        _git("push", "-q", "origin", "media", cwd=wd)
        sha = _git("rev-parse", "HEAD", cwd=wd)
    return [f"https://raw.githubusercontent.com/{REPO}/{sha}/media/{folder.name}/{p.name}" for p in paths]


# ── 게시 기록(media 브랜치 log.json) — 같은 날 같은 시리즈를 두 번 올리지 않게 ──────────────

LOG = "log.json"


def posted_log() -> list[dict]:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return []
    r = httpx.get(f"https://api.github.com/repos/{REPO}/contents/{LOG}", params={"ref": "media"}, timeout=30,
                  headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw+json"})
    if r.status_code != 200:
        return []
    try:
        return r.json()
    except ValueError:
        return []


def add_log(entry: dict) -> None:
    import json
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return
    remote = f"https://x-access-token:{token}@github.com/{REPO}.git"
    with tempfile.TemporaryDirectory() as d:
        wd = Path(d) / "media"
        _git("clone", "--depth", "1", "--branch", "media", remote, str(wd))
        _git("config", "user.name", "github-actions[bot]", cwd=wd)
        _git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com", cwd=wd)
        f = wd / LOG
        log = json.loads(f.read_text()) if f.exists() else []
        log = (log + [entry])[-300:]
        f.write_text(json.dumps(log, ensure_ascii=False, indent=1))
        _git("add", LOG, cwd=wd)
        _git("commit", "-q", "-m", f"게시 기록 {entry.get('date')} {entry.get('series')}", cwd=wd)
        _git("push", "-q", "origin", "media", cwd=wd)


# ── 인스타그램 ──────────────────────────────────────────────────────────────

def _call(c: httpx.Client, method: str, path: str, **params) -> dict:
    r = c.request(method, f"{API}/{path}", params={**params, "access_token": os.environ["IG_ACCESS_TOKEN"]})
    if r.status_code >= 400:
        raise PublishError(f"인스타 API {r.status_code}: {r.text[:300]}")
    return r.json()


def _wait(c: httpx.Client, ids: list[str], first: float = 3, every: float = 3, limit: float = 180) -> None:
    """컨테이너가 FINISHED 가 될 때까지 기다린다(인스타가 이미지를 내려받는 시간)."""
    time.sleep(first)
    end = time.time() + limit
    pending = set(ids)
    while pending and time.time() < end:
        for i in list(pending):
            st = _call(c, "GET", i, fields="status_code").get("status_code")
            if st == "FINISHED":
                pending.discard(i)
            elif st in ("ERROR", "EXPIRED"):
                raise PublishError(f"컨테이너 {i} 상태 {st}")
        if pending:
            time.sleep(every)
    if pending:
        raise PublishError(f"컨테이너 준비 시간 초과: {sorted(pending)}")


def recent_captions(limit: int = 30) -> list[str]:
    """계정에 실제로 올라간 글의 캡션(중복 게시 방지)."""
    with httpx.Client(timeout=30) as c:
        return [m.get("caption") or "" for m in _call(c, "GET", "me/media", fields="caption", limit=limit).get("data", [])]


def publish(urls: list[str], caption: str) -> str:
    """캐러셀 게시. 2~10장."""
    if not 2 <= len(urls) <= 10:
        raise PublishError(f"캐러셀은 2~10장(현재 {len(urls)}장)")
    uid = os.environ["IG_USER_ID"]
    with httpx.Client(timeout=60) as c:
        q = (_call(c, "GET", f"{uid}/content_publishing_limit", fields="quota_usage,config").get("data") or [{}])[0]
        if q.get("quota_usage", 0) >= (q.get("config") or {}).get("quota_total", 50):
            raise PublishError("24시간 게시 한도에 도달했습니다")
        children = [_call(c, "POST", f"{uid}/media", image_url=u, is_carousel_item="true")["id"] for u in urls]
        _wait(c, children)
        parent = _call(c, "POST", f"{uid}/media", media_type="CAROUSEL", children=",".join(children), caption=caption)["id"]
        _wait(c, [parent], first=4, every=4)
        try:
            return _call(c, "POST", f"{uid}/media_publish", creation_id=parent)["id"]
        except PublishError:
            # 오류를 돌려주면서 실제로는 올라가는 경우가 있다 — 계정에서 같은 캡션을 찾아본다
            time.sleep(15)
            head = caption.strip()[:60]
            for m in _call(c, "GET", "me/media", fields="id,caption", limit=5).get("data", []):
                if (m.get("caption") or "").strip()[:60] == head:
                    return m["id"]
            raise


def permalink(media_id: str) -> str | None:
    with httpx.Client(timeout=30) as c:
        return _call(c, "GET", media_id, fields="permalink").get("permalink")


def refresh_token() -> float | None:
    """장기 토큰 유효기간을 늘리고 남은 날수를 돌려준다(토큰 문자열은 그대로)."""
    with httpx.Client(timeout=30) as c:
        r = c.get("https://graph.instagram.com/refresh_access_token",
                  params={"grant_type": "ig_refresh_token", "access_token": os.environ["IG_ACCESS_TOKEN"]})
    if r.status_code >= 400:
        return None
    return float(r.json().get("expires_in", 0)) / 86400


# ── 텔레그램 ────────────────────────────────────────────────────────────────

def notify(text: str, photo: Path | None = None) -> None:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("[텔레그램 설정 없음]", text)
        return
    base = f"https://api.telegram.org/bot{token}"
    with httpx.Client(timeout=60) as c:
        if photo:
            with open(photo, "rb") as f:
                c.post(f"{base}/sendPhoto", data={"chat_id": chat, "caption": text[:1024]}, files={"photo": f})
        else:
            c.post(f"{base}/sendMessage", data={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"})
