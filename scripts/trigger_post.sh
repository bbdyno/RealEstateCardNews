#!/bin/zsh
# 맥에서 정시에 인스타 게시 워크플로를 부른다(GitHub 예약 실행은 몇 시간씩 밀린다).
# launchd 가 08:10 랭킹·10:10 지도30·12:10 예산30·14:40 지도20·15:40 랭킹2·18:10 릴스·19:40 현금·21:40 예산20 — 시각으로 시리즈를 정한다.
# 같은 날 같은 시리즈를 두 번 올리는 건 워크플로가 media 브랜치 log.json 으로 막는다.
H=$(date +%H)
if [ "$H" -lt 10 ]; then S=rank; elif [ "$H" -lt 11 ]; then S=dong; elif [ "$H" -lt 13 ]; then S=budget; elif [ "$H" -lt 15 ]; then S=dong2; elif [ "$H" -lt 17 ]; then S=rank2; elif [ "$H" -lt 19 ]; then S=reelday; elif [ "$H" -lt 21 ]; then S=cash; else S=budget2; fi
LOG="$HOME/Library/Logs/jipgapradar-post.log"
echo "$(date '+%F %T') $S" >> "$LOG"
/opt/homebrew/bin/gh workflow run post.yml --repo bbdyno/RealEstateCardNews -f series="$S" -f dry_run=false >> "$LOG" 2>&1
