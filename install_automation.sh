#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RUNTIME_DIR="$HOME/Library/Application Support/BackupOutlook"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs"
RUNTIME_SCRIPT="$RUNTIME_DIR/backup_outlook_professional.py"
UID_VALUE=$(id -u)

mkdir -p "$RUNTIME_DIR" "$LAUNCH_AGENTS_DIR" "$LOG_DIR"
install -m 755 "$PROJECT_DIR/backup_outlook_professional.py" "$RUNTIME_SCRIPT"

launchctl bootout "gui/$UID_VALUE/com.backupoutlook.onwake" 2>/dev/null || true
rm -f "$LAUNCH_AGENTS_DIR/com.backupoutlook.onwake.plist"

for template in "$PROJECT_DIR"/launchagents/*.plist.in; do
    output="$LAUNCH_AGENTS_DIR/$(basename "$template" .in)"
    sed -e "s|__RUNTIME_SCRIPT__|$RUNTIME_SCRIPT|g" \
        -e "s|__LOG_DIR__|$LOG_DIR|g" "$template" > "$output"
    plutil -lint "$output" >/dev/null
    label=$(basename "$output" .plist)
    launchctl bootout "gui/$UID_VALUE/$label" 2>/dev/null || true
    launchctl bootstrap "gui/$UID_VALUE" "$output"
done

echo "Automação instalada. Script operacional: $RUNTIME_SCRIPT"
echo "Agentes ativos: com.backupoutlook.daily e com.backupoutlook.login"