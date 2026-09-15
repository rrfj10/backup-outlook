#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RUNTIME_DIR="$HOME/Library/Application Support/BackupOutlook"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs"
RUNTIME_SCRIPT="$RUNTIME_DIR/backup_outlook_professional.py"
UID_VALUE=$(id -u)
PLISTBUDDY=/usr/libexec/PlistBuddy

mkdir -p "$RUNTIME_DIR" "$LAUNCH_AGENTS_DIR" "$LOG_DIR"
install -m 755 "$PROJECT_DIR/backup_outlook_professional.py" "$RUNTIME_SCRIPT"
if [ ! -f "$RUNTIME_DIR/.env" ] && [ -f "$PROJECT_DIR/.env" ]; then
    install -m 600 "$PROJECT_DIR/.env" "$RUNTIME_DIR/.env"
fi

ENV_FILE="$RUNTIME_DIR/.env"
config_value() {
    key=$1
    default=$2
    value=""
    if [ -f "$ENV_FILE" ]; then
        value=$(grep -E "^$key=" "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"')
    fi
    if [ -z "$value" ]; then
        value=$default
    fi
    printf '%s' "$value"
}
require_int_range() {
    name=$1
    value=$2
    min=$3
    max=$4
    case "$value" in
        ''|*[!0-9]*)
            echo "Configuração inválida: $name=\"$value\" precisa ser um número." >&2
            exit 1
            ;;
    esac
    if [ "$value" -lt "$min" ] || [ "$value" -gt "$max" ]; then
        echo "Configuração inválida: $name=$value fora do intervalo $min-$max." >&2
        exit 1
    fi
}

BACKUP_FREQUENCY=$(config_value BACKUP_FREQUENCY monthly)
BACKUP_HOUR=$(config_value BACKUP_HOUR 2)
BACKUP_MINUTE=$(config_value BACKUP_MINUTE 0)
BACKUP_DAY=$(config_value BACKUP_DAY 1)
BACKUP_WEEKDAY=$(config_value BACKUP_WEEKDAY 1)

require_int_range BACKUP_HOUR "$BACKUP_HOUR" 0 23
require_int_range BACKUP_MINUTE "$BACKUP_MINUTE" 0 59

case "$BACKUP_FREQUENCY" in
    daily|weekly|monthly) ;;
    *)
        echo "Configuração inválida: BACKUP_FREQUENCY=\"$BACKUP_FREQUENCY\" (use daily, weekly ou monthly)." >&2
        exit 1
        ;;
esac
if [ "$BACKUP_FREQUENCY" = "monthly" ]; then
    require_int_range BACKUP_DAY "$BACKUP_DAY" 1 28
fi
if [ "$BACKUP_FREQUENCY" = "weekly" ]; then
    require_int_range BACKUP_WEEKDAY "$BACKUP_WEEKDAY" 0 6
fi

# Migração: remove agentes de versões antigas (nomes/rotinas anteriores).
for old_label in com.backupoutlook.onwake com.backupoutlook.login com.backupoutlook.daily com.backupoutlook.monthly; do
    launchctl bootout "gui/$UID_VALUE/$old_label" 2>/dev/null || true
    rm -f "$LAUNCH_AGENTS_DIR/$old_label.plist"
done

for template in "$PROJECT_DIR"/launchagents/*.plist.in; do
    output="$LAUNCH_AGENTS_DIR/$(basename "$template" .in)"
    sed -e "s|__RUNTIME_SCRIPT__|$RUNTIME_SCRIPT|g" \
        -e "s|__LOG_DIR__|$LOG_DIR|g" "$template" > "$output"

    "$PLISTBUDDY" -c "Add :StartCalendarInterval dict" "$output"
    "$PLISTBUDDY" -c "Add :StartCalendarInterval:Hour integer $BACKUP_HOUR" "$output"
    "$PLISTBUDDY" -c "Add :StartCalendarInterval:Minute integer $BACKUP_MINUTE" "$output"
    case "$BACKUP_FREQUENCY" in
        weekly)
            "$PLISTBUDDY" -c "Add :StartCalendarInterval:Weekday integer $BACKUP_WEEKDAY" "$output"
            ;;
        monthly)
            "$PLISTBUDDY" -c "Add :StartCalendarInterval:Day integer $BACKUP_DAY" "$output"
            ;;
        daily) ;;
    esac

    plutil -lint "$output" >/dev/null
    label=$(basename "$output" .plist)
    launchctl bootout "gui/$UID_VALUE/$label" 2>/dev/null || true
    launchctl bootstrap "gui/$UID_VALUE" "$output"
done

echo "Automação instalada. Script operacional: $RUNTIME_SCRIPT"
case "$BACKUP_FREQUENCY" in
    daily)
        printf 'Agente ativo: com.backupoutlook.scheduled (diário) às %02d:%02d\n' "$BACKUP_HOUR" "$BACKUP_MINUTE"
        ;;
    weekly)
        printf 'Agente ativo: com.backupoutlook.scheduled (semanal, dia da semana %s [0=domingo]) às %02d:%02d\n' "$BACKUP_WEEKDAY" "$BACKUP_HOUR" "$BACKUP_MINUTE"
        ;;
    monthly)
        printf 'Agente ativo: com.backupoutlook.scheduled (mensal, dia %s) às %02d:%02d\n' "$BACKUP_DAY" "$BACKUP_HOUR" "$BACKUP_MINUTE"
        ;;
esac
