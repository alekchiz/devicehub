#!/usr/bin/env bash
#
# Бэкап БД МедКиоск (pg_dump) с автоочисткой старых дампов и проверкой целостности.
#
# Использование:
#   ./backup.sh               # создать бэкап и удалить дампы старше KEEP_DAYS
#   BACKUP_DIR=/var/backups ./backup.sh
#   KEEP_DAYS=30 ./backup.sh
#
# Восстановление: ./restore.sh <файл.dump>
#
set -euo pipefail

REMOTE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$REMOTE_DIR/backups}"
DB_USER="${DB_USER:-devicehub}"
DB_NAME="${DB_NAME:-device_hub}"
KEEP_DAYS="${KEEP_DAYS:-14}"
# Пароль БД берём из .env рядом со скриптом (контейнер db авторизуется по паролю).
DB_PASS="${DB_PASSWORD:-$(grep -E '^DB_PASSWORD=' .env | cut -d= -f2-)}"

mkdir -p "$BACKUP_DIR"
stamp="$(date +%Y%m%d_%H%M)"
tmp="$BACKUP_DIR/devicehub_${stamp}.dump.tmp"
file="$BACKUP_DIR/devicehub_${stamp}.dump"

echo "==> Дамп БД ($DB_NAME) в $file"

# Дамп пишем во временный файл: недобитый бэкап не должен считаться готовым.
if ! docker compose exec -T -e PGPASSWORD="$DB_PASS" db pg_dump -U "$DB_USER" "$DB_NAME" -Fc > "$tmp"; then
    echo "❌ Ошибка создания дампа" >&2
    rm -f "$tmp"
    exit 1
fi

# Страховка от «пустого» дампа (например, при обрыве контейнера или сети).
if [ ! -s "$tmp" ]; then
    echo "❌ Дамп пустой, бэкап не сохранён" >&2
    rm -f "$tmp"
    exit 1
fi

# Проверка читаемости дампа через pg_restore внутри контейнера.
# Заносим дамп в контейнер файлом — pg_restore из stdin через compose-exec не
# читает поток надёжно.
if ! docker compose exec -T db sh -c 'cat > /tmp/_chk.dump' < "$tmp" \
   || ! docker compose exec -T -e PGPASSWORD="$DB_PASS" db pg_restore -l /tmp/_chk.dump >/dev/null 2>&1; then
    echo "❌ Дамп не прошёл проверку pg_restore, буде удалён" >&2
    docker compose exec -T db rm -f /tmp/_chk.dump 2>/dev/null || true
    rm -f "$tmp"
    exit 1
fi
docker compose exec -T db rm -f /tmp/_chk.dump 2>/dev/null || true

mv "$tmp" "$file"
size="$(du -h "$file" | cut -f1)"
echo "OK: бэкап записан $file ($size)"

removed="$(find "$BACKUP_DIR" -name 'devicehub_*.dump' -mtime +"$KEEP_DAYS" -delete -printf '%f\n' 2>/dev/null | wc -l || true)"
echo "$KEEP_DAYS дней хранение; удалено старых дампов: $removed"
echo "Всего бэкапов: $(find "$BACKUP_DIR" -name 'devicehub_*.dump' | wc -l)"
