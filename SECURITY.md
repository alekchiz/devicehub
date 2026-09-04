# Безопасность: секреты и их ротация

Все секреты хранятся только в файле `.env` (он в `.dockerignore` и `.gitignore`).
В коде секретов нет: пароли и токены читаются из переменных окружения
(через `env_file: .env` в docker-compose и `python-dotenv` для локального запуска).

## Что лежит в `.env`

| Переменная | Назначение |
|------------|-----------|
| `DJANGO_SECRET_KEY` | подпись сессий, токенов CSRF и сброса пароля |
| `TELEGRAM_BOT_TOKEN` | токен Telegram-бота |
| `DEVICE_SSH_PASSWORD` | пароль SSH к ПАК |
| `MQTT_PASS` | пароль к MQTT-брокеру |
| `DB_PASSWORD` / `POSTGRES_PASSWORD` | пароль БД |

## Как ротировать

### 1. Telegram-бот
1. В Telegram: `@BotFather` → `/token` → выбери бота → новый токен.
2. Обнови `TELEGRAM_BOT_TOKEN` в `.env`.
3. `docker compose up -d --build bot`.

### 2. SSH-пароль к ПАК
1. Смени пароль на устройствах (и у пользователя `terminal` в sudoers).
2. Обнови `DEVICE_SSH_PASSWORD` в `.env`.
3. `docker compose up -d --build web`.

### 3. Пароль БД
Внимание: `POSTGRES_PASSWORD` Postgres читает только при **первом** создании тома.
Для уже существующей базы смени пароль вручную и синхронизируй:
```sql
ALTER USER devicehub WITH PASSWORD 'новый_надёжный_пароль';
```
Затем обнови `POSTGRES_PASSWORD` и `DB_PASSWORD` в `.env` и пересобери сервисы:
`docker compose up -d --build`.

### 4. `DJANGO_SECRET_KEY`
Сгенерируй длинную случайную строку (например, `python -c "import secrets; print(secrets.token_urlsafe(64))"`),
обнови `DJANGO_SECRET_KEY` в `.env`. После обновления все сессии станут невалидными —
пользователи перелогинятся один раз. Это нормально.

## После любой ротации
```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=20 bot     # проверить, что бот запустился
```

## Замечания по гигиене
- Никогда не коммить `.env` (он уже в `.gitignore`).
- Пароли/токены, которые когда-либо попадали в историю репозитория, считай скомпрометированными — ротируй.
- Rate-limit входа по IP реализован в `accounts/views.py`; кэш — общий (DatabaseCache),
  поэтому лимит работает одинаково для всех gunicorn-воркеров. Таблица `django_cache`
  создаётся автоматически при старте `web`.
