# Деплой бэкенда на Render — пошагово

Бэкенд уже лежит в репозитории: **https://github.com/Freger111/dz-bot-proxy**

## 1. Регистрация

1. <https://render.com> → **Get Started** → **Sign up with GitHub**.
2. Разреши Render доступ к своим репозиториям (можно только к `dz-bot-proxy`).

## 2. Создать Web Service

1. В дашборде: **New +** → **Web Service**.
2. **Connect a repository** → выбери `Freger111/dz-bot-proxy` → **Connect**.

## 3. Настройки сервиса

| Поле | Значение |
|---|---|
| **Name** | `dz-bot-proxy` |
| **Region** | Frankfurt (EU Central) |
| **Branch** | `main` |
| **Root Directory** | (пусто) |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| **Instance Type** | **Free** |

## 4. Переменные окружения

Прокрути до **Environment Variables** → **Add Environment Variable**.
Добавь по одной:

| Ключ | Значение |
|---|---|
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` |
| `LLM_API_KEY` | твой ключ OpenRouter (`sk-or-v1-...`) |
| `LLM_MODEL` | `nvidia/nemotron-3.5-super-vl:free` |
| `FALLBACK_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `FALLBACK_API_KEY` | твой ключ Gemini (`AQ...`) |
| `FALLBACK_MODEL` | `gemini-3.5-flash` |
| `RATE_PER_HOUR` | `30` |
| `RATE_PER_DAY` | `200` |
| `APP_TOKEN` | (можно оставить пустым) |

> Ключи возьми из файла `vk_bot/.env` — там `LLM_API_KEY` (Gemini) и `FALLBACK_API_KEY` (OpenRouter).

## 5. Создать и дождаться

1. Нажми **Create Web Service**.
2. Идёт сборка ~2–4 минуты. В логах должно быть:
   ```
   Uvicorn running on http://0.0.0.0:10000
   ```
3. Сверху появится адрес вида:
   ```
   https://dz-bot-proxy.onrender.com
   ```

## 6. Проверить

Открой в браузере:

```
https://dz-bot-proxy.onrender.com/health
```

Должно вернуться:

```json
{"ok": true, "model": "...", "keepalive": false, "limits": {...}}
```

## 7. Включить самопинг (чтобы не засыпал)

1. Render → твой сервис → **Environment**.
2. Добавь:
   ```
   PING_URL = https://dz-bot-proxy.onrender.com/health
   ```
3. **Save Changes** → Render передеплоит.
4. Проверь `/health` — теперь `"keepalive": true`.

## 8. Подставить адрес в приложение

В `android_app/app/src/main/java/com/dzbot/app/Config.kt`:

```kotlin
const val DEFAULT_BACKEND = "https://dz-bot-proxy.onrender.com"
```

Пересобрать APK — и всё, приложение работает у любого пользователя.

---

## Проблемы и решения

| Проблема | Причина | Решение |
|---|---|---|
| Build failed | нет `requirements.txt` | он в репозитории, проверь Root Directory |
| `Application failed to respond` | неверный Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| `/health` 502 | сервис ещё стартует | подожди 2 минуты |
| `LLM_API_KEY не задан` | забыл переменную | Environment → добавить |
| Долгий первый ответ | Render free засыпает | включи `PING_URL` (шаг 7) |
| 429 Too Many Requests | исчерпан лимит | подожди или подними `RATE_PER_HOUR` |

---

## Альтернативы

- **Railway** — New Project → Deploy from GitHub → тот же репозиторий, команда та же.
- **Koyeb** — New Service → GitHub → Dockerfile (он уже в репозитории) → порт `8000`.
- **Cloud Run** — Dockerfile уже есть, `gcloud run deploy`.
