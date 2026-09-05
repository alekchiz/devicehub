#!/usr/bin/env bash
#
# Восстановление БД МедКиоск из дампа, созданного backup.sh (custom format).
#
# Использование:
#   ./restore.sh <файл.dump>
#   ./restore.sh backups/devicehub_20260101_1200.dump
#   ./restore.sh <файл.dump> newschema
#
# ВНИМАНИЕ: перезаписывает текущую БД (DROP + CREATE). Рекомендуется сначала
# сделать свежий бэкап командой ./backup.sh.
#
set -euo pipefail

REMOTE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_USER="${DB_USER:-devicehub}"
DB_NAME="${DB_NAME:-device_hub}"

file="$1"
target="${2:-}"

if [ -z "${file:-}" ]; then
    echo "Использование: $0 <файл.dump> [схема/целевая_БД]"
    echo
    echo "Доступные бэкапы в $REMOTE_DIR/backups:"
    ls -1 "$REMOTE_DIR/backups"/devicehub_*.dump 2>/dev/null | sort -r || echo "(нет бэкапов)"
    exit 1
fi

if [ ! -f "$file" ]; then
    echo "❌ Файл не найден: $file" >&2
    exit 1
fi

if [ -n "$target" ]; then
    DB_NAME="$target"
fi

echo "Проверка дампа $file ..."
docker compose exec -T db pg_restore -l - < "$file" >/dev/null

echo "Восстановление БД '$DB_NAME' из $file ..."
docker compose exec -T db pg_restore \
    -U "$DB_USER" -d "$DB_NAME" --clean --if-exists --no-owner < "$file"

echo "✅ БД '$DB_NAME' восстановлена из $file"
echo
echo "Проверить: cd $REMOTE_DIR && docker compose exec -T db psql -U $DB_USER -d $DB_NAME -c 'select count(*) from devices_device;'"
