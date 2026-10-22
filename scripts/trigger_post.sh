#!/bin/zsh
# 맥미니 정시 게시 트리거. launchd 가 5분마다 부르고, scripts/slots.tsv 를 보고 때가 된 시리즈만 GitHub 워크플로(post.yml)로 보낸다.
# 카드·영상 제작과 게시는 GitHub 에서 돈다(맥미니가 꺼져 있으면 post.yml 의 GitHub 예약이 대신 돈다).
# 일정·코드를 바꾸면 매시 0~4분에 git pull 로 받아 오므로 맥미니에서 다시 설치할 필요가 없다.
# 같은 슬롯은 하루 한 번(상태 파일). 같은 시리즈 중복 게시는 워크플로가 media 브랜치 log.json 으로 한 번 더 막는다.
# 호출에 실패하면 상태를 남기지 않아 5분 뒤 다시 시도한다(슬롯 뒤 30분까지).
# 시험: JIP_NOW=12:41 JIP_GH=echo zsh scripts/trigger_post.sh
set -u
REPO="${0:A:h:h}"
LOG="${JIP_LOG:-$HOME/Library/Logs/jipgapradar-post.log}"
STATE="${JIP_STATE:-$HOME/Library/Logs/jipgapradar-post.state}"
GH="${JIP_GH:-$(command -v gh || echo /opt/homebrew/bin/gh)}"
WINDOW=30
log() { print -r -- "$(date '+%F %T') $*" >> "$LOG"; }

now="${JIP_NOW:-$(date +%H:%M)}"
now_m=$(( 10#${now%%:*} * 60 + 10#${now##*:} ))
if [[ -z "${JIP_NOW:-}" ]] && (( 10#${now##*:} < 5 )); then          # 매시 0~4분: 일정·코드 변경 받기
  git -C "$REPO" pull --ff-only -q >> "$LOG" 2>&1 || log "git pull 실패 — 지금 일정으로 계속"
fi
today=$(date +%F)
mkdir -p "${STATE:h}"; touch "$STATE"
while IFS=$'\t ' read -r t s _; do
  [[ -z "${t:-}" || "$t" == \#* ]] && continue
  slot_m=$(( 10#${t%%:*} * 60 + 10#${t##*:} ))
  (( now_m >= slot_m && now_m < slot_m + WINDOW )) || continue
  grep -qx "$today $t $s" "$STATE" && continue
  if "$GH" workflow run post.yml --repo bbdyno/RealEstateCardNews -f series="$s" -f dry_run=false >> "$LOG" 2>&1; then
    print -r -- "$today $t $s" >> "$STATE"
    log "$t $s 보냄"
  else
    log "$t $s 호출 실패 — 5분 뒤 다시"
  fi
done < "$REPO/scripts/slots.tsv"
tail -n 300 "$STATE" > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"     # 최근 기록만
