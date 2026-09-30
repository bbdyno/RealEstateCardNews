#!/bin/zsh
# 매일: 수집 → 빌드 → 링크 검사 → (scripts/deploy.sh 가 있으면) 배포. 로그: data/daily.log
set -e
cd "$(dirname "$0")/.."
PY=.venv/bin/python
LOG=data/daily.log
echo "=== $(date '+%Y-%m-%d %H:%M:%S') 시작" >> $LOG
$PY -m collector.collect >> $LOG 2>&1
# 샘플 데이터가 남아 있으면 멈춘다 — 가짜 숫자가 공개되지 않게
if [ -n "$($PY -c 'from collector import db; print(1 if db.has_demo(db.connect()) else "")')" ]; then
  echo "샘플 데이터가 남아 있어 빌드를 멈춥니다: .venv/bin/python -m collector.demo --clear" | tee -a $LOG >&2
  exit 1
fi
$PY -m web.build >> $LOG 2>&1
$PY scripts/check_links.py >> $LOG 2>&1
$PY scripts/check_html.py >> $LOG 2>&1
if [ -x scripts/deploy.sh ]; then scripts/deploy.sh >> $LOG 2>&1; fi
echo "=== $(date '+%Y-%m-%d %H:%M:%S') 끝" >> $LOG
