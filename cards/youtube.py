"""집값레이더 유튜브 채널에 릴스를 쇼츠로 함께 올린다(세로 1080×1920·3분 이하라 유튜브가 쇼츠로 분류한다).

환경변수 YT_CLIENT_ID · YT_CLIENT_SECRET · YT_REFRESH_TOKEN 이 모두 있을 때만 돈다. 없으면 조용히 건너뛴다.
채널 만들기와 토큰 발급은 사람 몫: 집값레이더 채널로 로그인한 브라우저에서

  .venv/bin/python -m cards.youtube auth <OAuth 데스크톱 클라이언트 JSON> --github

을 한 번 돌리면 새로 고침 토큰이 나온다. 세 값을 깃허브 저장소 비밀값에 넣으면 다음 업무지구 릴스부터 함께 올라간다.
실패해도 인스타 게시는 그대로 둔다(알림만).
"""
from __future__ import annotations

import http.server
import json
import os
import re
import sys
import urllib.parse
import webbrowser
from pathlib import Path

import httpx

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"   # 읽기는 연결된 채널 이름 확인용
CHANNEL = "집값레이더"
CATEGORY = "22"              # 인물·블로그(부동산 정보 채널이 흔히 쓰는 분류)


def ready() -> bool:
    return all(os.environ.get(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))


def _access_token(c: httpx.Client) -> str:
    r = c.post(TOKEN_URL, data={"client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"],
                                "refresh_token": os.environ["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"})
    r.raise_for_status()
    return r.json()["access_token"]


def title_from(caption: str) -> str:
    """캡션 첫 줄에서 제목(100자 이하, 유튜브가 막는 꺾쇠 제외)."""
    t = re.sub(r"[<>]", "", caption.strip().splitlines()[0]).strip()
    return t if len(t) <= 100 else t[:99] + "…"


def tags_from(caption: str) -> list[str]:
    return [t.lstrip("#") for t in re.findall(r"#\S+", caption)][:15]


def upload_short(mp4: Path, caption: str, privacy: str = "public") -> str | None:
    """올리고 영상 주소를 돌려준다. 설정이 없으면 None."""
    if not ready():
        return None
    meta = {"snippet": {"title": title_from(caption), "description": caption.replace("프로필 링크(jipgapradar.kr)", "jipgapradar.kr"),
                        "tags": tags_from(caption), "categoryId": CATEGORY, "defaultLanguage": "ko"},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    with httpx.Client(timeout=120) as c:
        auth = {"Authorization": f"Bearer {_access_token(c)}"}
        r = c.post(UPLOAD_URL, params={"uploadType": "resumable", "part": "snippet,status"},
                   headers={**auth, "X-Upload-Content-Type": "video/mp4", "Content-Type": "application/json; charset=UTF-8"},
                   content=json.dumps(meta, ensure_ascii=False).encode())
        r.raise_for_status()
        r = c.put(r.headers["Location"], headers={**auth, "Content-Type": "video/mp4"}, content=mp4.read_bytes(), timeout=600)
        r.raise_for_status()
        return f"https://youtube.com/shorts/{r.json()['id']}"


def auth(client_json: str, to_github: bool = False) -> None:
    """한 번만: 브라우저로 동의를 받아 새로 고침 토큰을 출력한다(내 컴퓨터 127.0.0.1 로 돌아온다)."""
    cfg = json.loads(Path(client_json).read_text())
    cfg = cfg.get("installed") or cfg.get("web") or cfg
    port = 8765
    redirect = f"http://127.0.0.1:{port}"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
        {"client_id": cfg["client_id"], "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
         "access_type": "offline", "prompt": "consent"})
    got: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            got.update(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("완료. 이 창을 닫아도 됩니다.".encode())

        def log_message(self, *a):
            pass

    print("브라우저에서 계정을 고르는 화면이 나오면 '집값레이더' 채널을 골라 동의해 주세요:\n" + url)
    webbrowser.open(url)
    with http.server.HTTPServer(("127.0.0.1", port), H) as srv:
        srv.handle_request()
    r = httpx.post(TOKEN_URL, data={"code": got["code"][0], "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                                    "redirect_uri": redirect, "grant_type": "authorization_code"})
    r.raise_for_status()
    tok = r.json()
    me = httpx.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "snippet", "mine": "true"},
                   headers={"Authorization": f"Bearer {tok['access_token']}"}).json()
    names = [x["snippet"]["title"] for x in me.get("items", [])]
    if CHANNEL not in names:           # 다른 채널을 고르면 비밀값을 건드리지 않는다
        raise SystemExit(f"연결된 채널이 {names or '없음'} 입니다. 동의 화면에서 '{CHANNEL}' 채널을 골라 다시 해 주세요.")
    print("연결된 채널:", CHANNEL)
    vals = {"YT_CLIENT_ID": cfg["client_id"], "YT_CLIENT_SECRET": cfg["client_secret"], "YT_REFRESH_TOKEN": tok["refresh_token"]}
    if to_github:                      # 값을 화면에 찍지 않고 바로 저장소 비밀값으로
        import subprocess
        for k, v in vals.items():
            subprocess.run(["gh", "secret", "set", k, "--repo", "bbdyno/RealEstateCardNews"], input=v, text=True, check=True)
        print("깃허브 저장소 비밀값 세 개를 넣었습니다:", ", ".join(vals))
        return
    print("\n깃허브 저장소 비밀값에 넣을 세 값:")
    for k, v in vals.items():
        print(k, "=", v)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "auth":
        auth(sys.argv[2], "--github" in sys.argv)
    else:
        print("사용법: python -m cards.youtube auth <클라이언트 JSON> [--github]")
