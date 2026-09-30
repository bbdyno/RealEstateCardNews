"""dist/ 의 HTML 태그 짝이 맞는지 검사한다(닫는 태그가 어긋나면 카드 밖으로 내용이 흘러나온다)."""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from html.parser import HTMLParser
from pathlib import Path

DIST = Path(__file__).resolve().parents[1] / "dist"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr",
        "path", "rect", "circle", "line", "stop", "polyline"}


class Checker(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack: list[tuple[str, int]] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1][0] != tag:
            top = self.stack[-1] if self.stack else None
            self.errors.append(f"줄 {self.getpos()[0]}: </{tag}> 인데 열린 것은 {top}")
            for i in range(len(self.stack) - 1, -1, -1):        # 가장 가까운 짝까지 닫고 계속
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    break
        else:
            self.stack.pop()


def check(page: Path) -> tuple[str, list[str]] | None:
    ch = Checker()
    ch.feed(page.read_text(encoding="utf-8"))
    if ch.errors or ch.stack:
        return str(page.relative_to(DIST)), ch.errors[:3] + ([f"안 닫힘: {ch.stack[-3:]}"] if ch.stack else [])
    return None


def main() -> int:
    """페이지가 4만 개가 넘어 코어마다 나눠 검사한다(한 코어로는 3분, 4코어면 1분 안쪽)."""
    pages = list(DIST.rglob("*.html"))
    with ProcessPoolExecutor() as ex:
        bad = dict(r for r in ex.map(check, pages, chunksize=500) if r)
    print(f"검사 {len(pages)}개, 문제 {len(bad)}개")
    for k, v in list(bad.items())[:10]:
        print(" ", k, v)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
