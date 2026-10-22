"""사이트 미리보기 — 실제 jipgapradar.kr 페이지를 휴대폰 화면으로 찍어 카드뉴스 마지막 장·릴스 마지막 장면에 쓴다.

  .venv/bin/python -m cards.sitecard /c/11110-2203/ "1위 단지 실거래 전부"   → out/cards/site/…jpg

인스타 글·이미지 속 주소는 눌리지 않는다(누를 수 있는 건 프로필 링크뿐). 그래서 '어떤 화면이 기다리는지'를 보여 주고
프로필 링크로 보낸다. 페이지를 못 찍으면(사이트 장애·네트워크) None 을 돌려주고, 부르는 쪽은 사이트 장 없이 진행한다.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from collector import db
from web.build import load_cfg

from .budget import CHROME, OUT, env, shoot

SITE_W, SITE_H, SCALE = 390, 1600, 2        # 아이폰 너비로 찍어 두 배 해상도 → 780×3200


def base_url() -> str:
    return load_cfg()["site"]["base_url"].rstrip("/")


def shoot_page(path: str, out: Path, height: int = SITE_H) -> Path | None:
    """사이트 한 페이지를 휴대폰 크기로 찍는다. 실패하거나 빈 화면이면 None."""
    url = base_url() + (path if path.startswith("/") else "/" + path)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-sandbox",
                        f"--force-device-scale-factor={SCALE}", f"--window-size={SITE_W},{height}",
                        "--virtual-time-budget=10000", "--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
                        f"--screenshot={out}", url], check=True, capture_output=True, timeout=120)
    except (subprocess.SubprocessError, OSError) as e:
        print(f"사이트 화면 못 찍음({url}): {e}", file=sys.stderr)
        return None
    return out if out.exists() and out.stat().st_size > 30_000 else None


def card(path: str, lead: str, slug: str) -> Path | None:
    """카드뉴스 마지막 장: 휴대폰 속 실제 페이지 + 주소 + 프로필 링크 안내. 못 만들면 None."""
    d = OUT / "site"
    (d / slug).mkdir(parents=True, exist_ok=True)
    shot = shoot_page(path, d / f"{slug}-page.png")
    if not shot:
        return None
    files, _ = shoot(env(), [("site_card", {})],
                     dict(lead=lead, shot=shot.as_uri(), url=base_url().split("//", 1)[-1] + (path if path != "/" else ""),
                          logo=(db.ROOT / "web" / "static" / "logo.svg").as_uri()),
                     d / slug)
    return files[0] if files else None


if __name__ == "__main__":
    print(card(sys.argv[1] if len(sys.argv) > 1 else "/", sys.argv[2] if len(sys.argv) > 2 else "전국 아파트 실거래가", "demo"))
