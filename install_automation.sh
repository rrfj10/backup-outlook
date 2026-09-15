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
if [ ! -f "$RUNTIME_DIR/.env" ] && [ -f "$PROJECT_DIR/.env" ]; then
    install -m 600 "$PROJECT_DIR/.env" "$RUNTIME_DIR/.env"
fi

ENV_FILE="$RUNTIME_DIR/.env"
config_value() {
    key=$1
    default=$2
    if [ -f "$ENV_FILE" ]; then
        value=$(grep -E "^$key=" "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"')
    fi
    if [ -z "${value:-}" ]; then
        value=$default
    fi
    printf '%s' "$value"
}
BACKUP_DAY=$(config_value BACKUP_DAY 1)
BACKUP_HOUR=$(config_value BACKUP_HOUR 2)
BACKUP_MINUTE=$(config_value BACKUP_MINUTE 0)

launchctl bootout "gui/$UID_VALUE/com.backupoutlook.onwake" 2>/dev/null || true
rm -f "$LAUNCH_AGENTS_DIR/com.backupoutlook.onwake.plist"
launchctl bootout "gui/$UID_VALUE/com.backupoutlook.login" 2>/dev/null || true
rm -f "$LAUNCH_AGENTS_DIR/com.backupoutlook.login.plist"
launchctl bootout "gui/$UID_VALUE/com.backupoutlook.daily" 2>/dev/null || true
rm -f "$LAUNCH_AGENTS_DIR/com.backupoutlook.daily.plist"

for template in "$PROJECT_DIR"/launchagents/*.plist.in; do
    output="$LAUNCH_AGENTS_DIR/$(basename "$template" .in)"
    sed -e "s|__RUNTIME_SCRIPT__|$RUNTIME_SCRIPT|g" \
        -e "s|__LOG_DIR__|$LOG_DIR|g" \
        -e "s|__BACKUP_DAY__|$BACKUP_DAY|g" \
        -e "s|__BACKUP_HOUR__|$BACKUP_HOUR|g" \
        -e "s|__BACKUP_MINUTE__|$BACKUP_MINUTE|g" "$template" > "$output"
    plutil -lint "$output" >/dev/null
    label=$(basename "$output" .plist)
    launchctl bootout "gui/$UID_VALUE/$label" 2>/dev/null || true
    launchctl bootstrap "gui/$UID_VALUE" "$output"
done

echo "Automação instalada. Script operacional: $RUNTIME_SCRIPT"
printf 'Agente ativo: com.backupoutlook.monthly no dia %s às %02d:%02d\n' "$BACKUP_DAY" "$BACKUP_HOUR" "$BACKUP_MINUTE"