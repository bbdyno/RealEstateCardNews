"""모션 그래픽 릴스 — showreel 엔진(third_party/showreel, 서브모듈)으로 랭킹 카운트다운 영상을 만든다.

  .venv/bin/python -m reels.build rank highs 서울            → out/reels/motion-rank-highs-서울.mp4
  .venv/bin/python -m reels.build rank highs 서울 --stills 1,4,13,18   (확인용 스틸만)

흐름: DB 순위(cards.rank.pick) → data.js · timeline.js → new_project.py 로 최신 엔진·글꼴을 깐 작업 폴더
     → 우리 장면(templates/rank/scenes.js·brand.css) → 큐에 맞춘 배경음 합성(synth_music.py, 무료)
     → 렌더(render.mjs) → 음량 맞추기 → 마감(finish.py) → 검수(motion_check·qa_check).

엔진 파일은 고치지 않는다. 서브모듈을 올리면(scripts/update_showreel.sh) 다음 렌더부터 새 엔진이 그대로 쓰인다.
숫자·이름은 여기서 사이트와 같은 함수(web.fmt)로 만든 문자열만 화면에 나간다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from cards import rank, sitecard
from cards.budget import CHROME
from collector import db
from web import fmt

HERE = Path(__file__).parent
SR = db.ROOT / "third_party" / "showreel"
SCRIPTS = SR / "scripts"
OUT = db.ROOT / "out" / "reels"
BPM = 100
BAR = 60 / BPM * 4                 # 2.4초 — 장면 경계를 마디에 맞춘다
PY = sys.executable

NAMES = {"highs": ("이전 최고", "신고가"), "drops": ("3년 최고", "실거래"), "cancels": ("직전 최고", "해제된 값")}


def rows_for(fmt_: str, sido: str, today: dt.date, n: int = 5) -> list[dict]:
    rows = rank.pick(fmt_, sido, today)[:n]
    out = []
    for r in rows:
        up = r["up"]
        arrow = "▼" if fmt_ == "drops" else "▲"
        y, m, d = (int(x) for x in r["ymd"].split("-"))
        out.append(dict(rank=r["rank"], name=r["name"], loc=f"{r['gu']} {r['umd']}".strip(), py=r["py"],
                        price=int(r["price"]), prev=int(r["prev"]),
                        price_label=fmt.won(r["price"]), prev_label=fmt.won(r["prev"]),
                        up_label=f"{arrow} {abs(up) * 100:.1f}%", prev_name=NAMES[fmt_][0], now_name=NAMES[fmt_][1],
                        meta=f"{m}.{d} 계약", href=r.get("href", "/")))
    return out


def plan(n: int, outro_bars: int = 1) -> dict:
    """장면 시각(초). k위는 한 마디, 1위는 두 마디, 오프닝 한 마디, 마무리는 사이트 화면이 있으면 두 마디."""
    cues = {"intro": 0.0}
    for k in range(n, 0, -1):
        cues[f"r{k}"] = round(BAR * (n - k + 1), 3)
    cues["outro"] = round(cues["r1"] + BAR * 2, 3)
    cues["end"] = round(cues["outro"] + BAR * outro_bars, 3)
    return cues


def music_spec(cues: dict, n: int) -> dict:
    r1 = cues["r1"]
    ev = [{"t": cues[f"r{k}"], "type": "hit"} for k in range(n, 1, -1)]
    ev += [{"t": round(r1 - 1.6, 2), "type": "riser", "dur": 1.6}, {"t": r1, "type": "boom"},
           {"t": round(r1 + 2.4, 2), "type": "hit"}, {"t": round(cues["outro"] + 0.2, 2), "type": "chime"}]
    return {"duration": cues["end"], "mood": "pulse", "bpm": BPM,
            "sections": [{"start": 0, "energy": 0.35}, {"start": cues[f"r{n}"], "energy": 0.55},
                         {"start": cues.get("r3", r1), "energy": 0.7}, {"start": r1, "energy": 0.95},
                         {"start": cues["outro"], "energy": 0.4}],
            "events": ev, "fade_in": 0.3, "fade_out": 1.6}


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    env = {**os.environ, "REEL_CHROME_PATH": os.environ.get("REEL_CHROME_PATH", CHROME)}
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, env=env, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"{Path(str(cmd[1])).name} 실패({r.returncode}):\n{(r.stdout + r.stderr)[-1500:]}")
    return r


def prepare(work: Path, data: dict, cues: dict, site_png: Path | None = None) -> Path:
    """작업 폴더: 최신 엔진·글꼴(new_project.py) + 우리 장면·색 + 데이터·큐."""
    if work.exists():
        shutil.rmtree(work)
    run([PY, SCRIPTS / "new_project.py", work, "--ratio", "9:16", "--duration", cues["end"], "--fps", "30"])
    reel = work / "reel"
    tpl = HERE / "templates" / "rank"
    shutil.copy(tpl / "scenes.js", reel / "scenes.js")
    shutil.copy(tpl / "brand.css", reel / "brand.css")
    page = (reel / "index.html").read_text(encoding="utf-8")       # 엔진의 index.html 을 그대로 두고 두 줄만 끼운다
    page = page.replace("</head>", '<link rel="stylesheet" href="brand.css">\n</head>', 1)
    page = page.replace('<script src="scenes.js"></script>', '<script src="data.js"></script>\n<script src="scenes.js"></script>', 1)
    (reel / "index.html").write_text(page, encoding="utf-8")
    if site_png:
        shutil.copy(site_png, reel / "site.png")
    (reel / "data.js").write_text("window.DATA = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
    beats = [round(i * 60 / BPM, 3) for i in range(int(cues["end"] * BPM / 60) + 1)]
    tl = {"cues": cues, "vo": [], "music": {"bpm": BPM, "beats": beats, "downbeats": beats[::4], "hits": []}}
    (reel / "timeline.js").write_text("window.TL = " + json.dumps(tl) + ";\n", encoding="utf-8")
    return reel


def build(kind: str, fmt_: str, sido: str, today: dt.date | None = None, stills: str | None = None,
          sub: int = 2, n: int = 5, strict: bool = False, rows: list[dict] | None = None) -> Path:
    if kind != "rank" or fmt_ not in NAMES:
        raise SystemExit(f"지원: rank {'|'.join(NAMES)} (받은 값: {kind} {fmt_})")
    today = today or dt.date.today()
    rows = rows if rows is not None else rows_for(fmt_, sido, today, n)
    if len(rows) < 3:
        raise SystemExit(f"{sido} {fmt_}: 순위가 {len(rows)}개뿐이라 만들지 않는다")
    f = rank.FORMATS[fmt_]
    slug = f"motion-{kind}-{fmt_}-{sido}"
    work = OUT / "work" / slug
    top = rows[0]
    site_png = sitecard.shoot_page(top["href"], OUT / "work" / f"{slug}-site.png")   # 1위 단지 실제 페이지(못 찍으면 글자 마무리)
    data = dict(sido=sido, fmt=fmt_, head=f["head"], sub=f["sub"], accent=f["ac"], asof=f"{today.month}.{today.day} 신고분까지",
                outro_lead=f"{sido} 전체 순위·지도는", source="국토교통부 실거래가 공개 자료 기준", rows=rows,
                site=dict(img="site.png", lead=f"{top['name']} 실거래", url=sitecard.base_url().split("//", 1)[-1] + top["href"])
                if site_png else None)
    cues = plan(len(rows), 2 if site_png else 1)
    reel = prepare(work, data, cues, site_png)
    if stills:
        run(["node", SCRIPTS / "render.mjs", "--dir", reel, "--stills", stills, "--outdir", work / "stills"])
        print(work / "stills")
        return work / "stills"

    spec = work / "music.json"
    spec.write_text(json.dumps(music_spec(cues, len(rows))), encoding="utf-8")
    run([PY, SCRIPTS / "synth_music.py", "music", spec, work / "music_raw.wav"])
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", work / "music_raw.wav", "-af", "alimiter=limit=0.7:level=false,loudnorm=I=-14:TP=-3:LRA=9",
         "-ar", "48000", work / "music.wav"])                                     # 릴스 기준 음량(-14 LUFS)
    run(["node", SCRIPTS / "render.mjs", "--dir", reel, "--out", work / "video.mp4", "--sub", str(sub)], timeout=3600)
    OUT.mkdir(parents=True, exist_ok=True)
    run([PY, SCRIPTS / "finish.py", "--video", work / "video.mp4", "--audio", work / "music.wav", "--name", slug,
         "--outdir", OUT, "--no-web"])
    mp4 = OUT / f"{slug}.mp4"
    tame_peak(mp4)
    mc = run([PY, SCRIPTS / "motion_check.py", mp4, "--skip-end", "1.5"])
    qa = run([PY, SCRIPTS / "qa_check.py", mp4, "--qa", work / "qa"])
    print((mc.stdout + "\n" + qa.stdout).strip()[-1800:])
    problems = verdict(mc.stdout, work / "qa" / "qa_report.md")
    if strict and problems:
        raise RuntimeError("영상 자동 검수 미통과 — 올리지 않는다:\n- " + "\n- ".join(problems))
    return mp4


def true_peak(path: Path) -> float | None:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    m = re.search(r"Peak:\s+(-?[\d.]+)", r[r.rfind("Summary:"):])
    return float(m.group(1)) if m else None


def tame_peak(mp4: Path, limit: float = -1.2) -> None:
    """AAC 인코딩은 피크를 0.5~1dB 올린다(ffmpeg 판마다 다름 — 맥 -1.6 이 리눅스에선 -0.8). 넘으면 오디오만 낮춰 다시 싼다(영상 복사)."""
    for _ in range(3):
        tp = true_peak(mp4)
        if tp is None or tp <= limit:
            return
        tmp = mp4.with_name(mp4.stem + ".tmp.mp4")
        run(["ffmpeg", "-v", "error", "-y", "-i", mp4, "-c:v", "copy", "-af", f"volume={limit - 0.6 - tp:.2f}dB",
             "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-movflags", "+faststart", tmp])
        tmp.replace(mp4)


def verdict(motion_out: str, report: Path) -> list[str]:
    """엔진 검수 결과에서 걸린 항목만 뽑는다. 움직임 경고(△·✗)와 보고서 '고칠 것'의 빈 체크박스."""
    out = [ln.strip() for ln in motion_out.splitlines() if ln.strip().startswith(("△", "✗"))]
    if report.exists():
        sec = report.read_text(encoding="utf-8").split("## 고칠 것", 1)
        if len(sec) == 2:
            out += [ln.strip()[6:] for ln in sec[1].split("\n## ", 1)[0].splitlines() if ln.strip().startswith("- [ ]")]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind")
    ap.add_argument("fmt")
    ap.add_argument("sido")
    ap.add_argument("--stills")
    ap.add_argument("--sub", type=int, default=2, help="모션 블러 부분 프레임 수(1 이면 끔)")
    ap.add_argument("--date")
    ap.add_argument("--strict", action="store_true", help="엔진 검수에서 하나라도 걸리면 실패(게시·엔진 업데이트 시험용)")
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.date) if a.date else None
    print(build(a.kind, a.fmt, a.sido, today, a.stills, a.sub, strict=a.strict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
