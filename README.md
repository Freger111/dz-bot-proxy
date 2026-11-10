# ДЗ-Бот · бэкенд-прокси (для многих пользователей)

Сервер, который держит ключ LLM у себя, ограничивает частоту запросов
и сам переключается на запасного провайдера.

## Что умеет

- `POST /api/chat` — принимает сообщения, добавляет системный промпт, ходит в LLM.
- `GET /health` — проверка и текущие лимиты.
- **Лимиты** на устройство/IP: `RATE_PER_HOUR` (30), `RATE_PER_DAY` (200).
- **Фолбэк провайдера** — если OpenRouter упал/упёрся в лимит, пробует Gemini.
- **Самопинг** — `PING_URL` держит бесплатный Render активным.
- **`X-Device-Id`** — приложение само присылает id, чтобы лимит считался по устройству.

## Запуск локально

```bash
cd proxy_backend
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --host 0.0.0.0 --port 8000
```

Проверка: <http://127.0.0.1:8000/health>

## Переменные окружения

| Переменная | Описание |
|---|---|
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | основной провайдер |
| `FALLBACK_BASE_URL` / `FALLBACK_API_KEY` / `FALLBACK_MODEL` | запасной (необязательно) |
| `APP_TOKEN` | простой токен доступа (приложение шлёт `X-App-Token`) |
| `RATE_PER_HOUR` | запросов в час на устройство (по умолчанию 30) |
| `RATE_PER_DAY` | запросов в сутки на устройство (200) |
| `PING_URL` | публичный `https://…/health` для самопинга |
| `PING_INTERVAL` | интервал пинга в секундах (600) |

## Лимиты

Считаются в памяти процесса по ключу `X-Device-Id` (или IP).
При перезапуске сервиса сбрасываются.

Если нужно хранить лимиты постоянно — замени словарь на Redis:

```python
# вместо _buckets используй redis:
# r.zadd(key, {now: now}); r.zremrangebyscore(key, 0, now - 86400)
```

## Деплой на Render

1. Залей `proxy_backend` в GitHub.
2. Render → New → Web Service → репозиторий.
3. Build: `pip install -r requirements.txt`
4. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Environment:
   - `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`
   - `FALLBACK_BASE_URL`, `FALLBACK_API_KEY`, `FALLBACK_MODEL` (по желанию)
   - `APP_TOKEN` (по желанию)
   - `PING_URL=https://<твой-сервис>.onrender.com/health`
6. Задеплоен → проверь `/health`.

## Нагрузка

- Один бесплатный инстанс тянет десятки пользователей (модель — узкое место, не сервер).
- Для сотен/тысяч — переезжай на **Cloud Run** / **Railway** / VPS,
  добавь Redis для лимитов и несколько инстансов.

## Безопасность

- Ключ LLM только в переменных окружения сервера.
- `APP_TOKEN` — чтобы прокси не использовали чужие.
- Лимиты защищают от перерасхода ключа.
