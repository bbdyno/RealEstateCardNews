#!/bin/zsh
# 매일 06:30 에 scripts/daily.sh 를 돌리는 LaunchAgent 를 설치한다(맥이 잠들어 있으면 깨어난 뒤 한 번 돈다).
#   scripts/install_launchagent.sh          설치·갱신
#   scripts/install_launchagent.sh remove   제거
set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
LABEL="com.bbdyno.realestate.daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
if [[ "$1" == "remove" ]]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true; rm -f "$PLIST"; echo "제거 완료"; exit 0
fi
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/zsh</string><string>$ROOT/scripts/daily.sh</string></array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>$ROOT/data/launchd.log</string>
  <key>StandardErrorPath</key><string>$ROOT/data/launchd.log</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "설치 완료: 매일 06:30. 바로 한 번 돌리려면 launchctl kickstart gui/$(id -u)/$LABEL"
