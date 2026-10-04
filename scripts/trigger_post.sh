#!/bin/zsh
# 맥에서 정시에 인스타 게시 워크플로를 부른다(GitHub 예약 실행은 몇 시간씩 밀린다).
# launchd(com.bbdyno.jipgapradar.post)가 08:10 · 12:10 · 15:40 · 19:40 · 21:40 에 실행 — 시각으로 시리즈를 정한다.
# 같은 날 같은 시리즈를 두 번 올리는 건 워크플로가 media 브랜치 log.json 으로 막는다.
H=$(date +%H)
if [ "$H" -lt 10 ]; then S=rank; elif [ "$H" -lt 14 ]; then S=budget; elif [ "$H" -lt 17 ]; then S=rank2; elif [ "$H" -lt 21 ]; then S=cash; else S=budget2; fi
LOG="$HOME/Library/Logs/jipgapradar-post.log"
echo "$(date '+%F %T') $S" >> "$LOG"
/opt/homebrew/bin/gh workflow run post.yml --repo bbdyno/RealEstateCardNews -f series="$S" -f dry_run=false >> "$LOG" 2>&1
