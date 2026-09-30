"""dist/ 안의 모든 페이지에서 내부 링크(/로 시작)가 실제 파일로 이어지는지 검사한다."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

DIST = Path(__file__).resolve().parents[1] / "dist"
HREF = re.compile(r'(?:href|src)="(/[^"#]*)"')
SCRIPT = re.compile(r"<script\b.*?</script>", re.S)       # 스크립트 안의 문자열 조립은 링크가 아니다


def target(path: str) -> Path:
    p = unquote(urlparse(path).path)
    f = DIST / p.lstrip("/")
    return f / "index.html" if p.endswith("/") else f


def main() -> int:
    broken: dict[str, set[str]] = {}
    pages = list(DIST.rglob("*.html"))
    for page in pages:
        for link in HREF.findall(SCRIPT.sub("", page.read_text(encoding="utf-8"))):
            if not target(link).exists():
                broken.setdefault(link, set()).add(str(page.relative_to(DIST)))
    print(f"페이지 {len(pages)}개 검사, 깨진 링크 {len(broken)}개")
    for link, where in sorted(broken.items())[:30]:
        print(f"  {link}  ← {sorted(where)[:3]}")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
