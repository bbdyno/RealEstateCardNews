#!/bin/zsh
# 맥미니 게시 트리거(launchd) 설치·갱신 — 한 번만 실행하면 된다. 그 뒤로 일정은 scripts/slots.tsv 를 고쳐 올리기만 하면 된다.
#   zsh scripts/install_post_agent.sh            설치·갱신(5분마다 trigger_post.sh)
#   zsh scripts/install_post_agent.sh --remove   제거
set -e
LABEL=com.bbdyno.jipgapradar.post
REPO="${0:A:h:h}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/jipgapradar-post.log"
if [[ "${1:-}" == "--remove" ]]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true; rm -f "$PLIST"; echo "제거 완료"; exit 0
fi
[[ "$REPO" == "$HOME/Documents"* || "$REPO" == "$HOME/Desktop"* ]] && { echo "⚠️ launchd 는 문서·데스크톱 폴더를 못 읽습니다. 저장소를 ~/Repository 등으로 옮기세요."; exit 1; }
command -v gh >/dev/null || [[ -x /opt/homebrew/bin/gh ]] || { echo "⚠️ gh 가 없습니다: brew install gh && gh auth login"; exit 1; }
chmod +x "$REPO/scripts/trigger_post.sh"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/zsh</string><string>$REPO/scripts/trigger_post.sh</string></array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>StartInterval</key><integer>300</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PL
plutil -lint "$PLIST" >/dev/null
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "✅ 설치 완료 — 5분마다 일정 확인($REPO/scripts/slots.tsv)"
(gh auth status >/dev/null 2>&1 || /opt/homebrew/bin/gh auth status >/dev/null 2>&1) && echo "✅ gh 로그인 확인" || echo "⚠️ gh 로그인이 필요합니다: gh auth login"
echo "오늘 일정:"; grep -vE '^\s*(#|$)' "$REPO/scripts/slots.tsv" | sed 's/^/  /'
