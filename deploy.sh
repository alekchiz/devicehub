#!/usr/bin/env bash
#
# Деплой Device Hub на сервер: rsync + пересборка Docker + проверка логов.
#
# Использование:
#   ./deploy.sh                        # синк + build + статус + логи
#   DRY_RUN=1 ./deploy.sh              # только показать, что синхронизируется
#   SERVER=user@host ./deploy.sh       # без редактирования скрипта
#   REMOTE_DIR=/opt/devicehub ./deploy.sh
#
set -euo pipefail

# ----- Параметры (можно переопределить через переменные окружения) -----
SERVER="${SERVER:-root@support-pak.ru}"
REMOTE_DIR="${REMOTE_DIR:-/app/devicehub}"
LOCAL_DIR="${LOCAL_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

# Что НЕ переносим на сервер
EXCLUDES=(--exclude venv --exclude __pycache__ --exclude '*.py[cod]'
          --exclude .git --exclude .DS_Store --exclude mqtt.log)

# .env не исключаем — он единственный источник секретов и обязан быть на сервере.

if [[ ! -f "$LOCAL_DIR/.env" ]]; then
  echo "!! Не найден $LOCAL_DIR/.env — секреты не синхронизируются."
  echo "   Создайте .env из .env.example и укажите реальные значения, затем повторите."
  exit 1
fi

RSYNC_FLAGS=(-az --delete)
if [[ "${DRY_RUN:-0}" == "1" ]]; then
  RSYNC_FLAGS+=(--dry-run)
fi

echo "==> Локальный каталог: $LOCAL_DIR"
echo "==> Цель:            ${SERVER}:${REMOTE_DIR}"
echo "==> Синхронизация проекта..."
rsync "${RSYNC_FLAGS[@]}" "${EXCLUDES[@]}" -e ssh "$LOCAL_DIR"/ "${SERVER}:${REMOTE_DIR}/"

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo "==> DRY_RUN: на сервер ничего не отправлено."
  exit 0
fi

echo "==> [сервер] Пересборка и перезапуск сервисов..."
ssh "$SERVER" "cd $REMOTE_DIR && docker compose up -d --build"

echo "==> [сервер] Статус сервисов (healthcheck):"
ssh "$SERVER" "cd $REMOTE_DIR && docker compose ps"

echo "==> [сервер] Логи web / bot / mqtt_listener (по 20 строк):"
ssh "$SERVER" "cd $REMOTE_DIR && docker compose logs --tail=20 web bot mqtt_listener"

echo "==> Деплой завершён."
