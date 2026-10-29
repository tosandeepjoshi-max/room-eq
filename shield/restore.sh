#!/bin/bash
# Re-applies the NVIDIA Shield setup (Android 11) after a factory reset. See shield/README.md.
# Run from the PC (Git Bash) or the Pi:  bash shield/restore.sh [ip:5555]
# Before: Developer options > Network debugging on, Projectivy Launcher installed from the Play Store.
# Safe to run again: steps already done only print a failure line.
HOST=${1:-192.168.110.211:5555}
APK="$(dirname "$0")/sleephome/sleephome.apk"
A="adb -s $HOST"

adb connect "$HOST" >/dev/null
if [ "$($A get-state 2>/dev/null)" != device ]; then
  echo "No ADB access to $HOST. Accept the prompt on the TV (Always allow) and run again."
  exit 1
fi
if ! $A shell pm path com.spocky.projengmenu >/dev/null; then
  echo "Install Projectivy Launcher from the Play Store first."
  exit 1
fi

echo "== Remove apps (Amazon Music and YouTube TV stay on purpose)"
for p in air.com.vudu.air.DownloaderTablet com.google.android.music com.google.android.videos \
         com.google.android.play.games com.nvidia.tegrazone3 com.nvidia.nvgamecast \
         com.nvidia.stats com.nvidia.feedback com.google.android.feedback; do
  echo "$p: $($A shell pm uninstall --user 0 "$p" 2>&1)"
done

echo "== Disable the stock launcher and Google recommendations (Projectivy becomes Home)"
for p in com.google.android.tvlauncher com.google.android.tvrecommendations; do
  $A shell pm disable-user --user 0 "$p"
done

echo "== Install Sleep Home and turn on both accessibility services"
$A install -r "$APK"
$A shell settings put secure enabled_accessibility_services \
  "com.spocky.projengmenu/com.spocky.projengmenu.services.ProjectivyAccessibilityService:com.joshi.sleephome/com.joshi.sleephome.SleepHomeService"
$A shell settings put secure accessibility_enabled 1

echo "== Check"
echo "Home app: $($A shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME | tail -1)"
sleep 3
$A shell dumpsys accessibility | grep -o "label=[^,]*" | sed 's/^/Bound: /'
echo "If Projectivy is not listed as bound, restart the Shield ($A reboot) and check again."
