"""Бэкенд-прокси для ДЗ-Бота (мультипользовательский).

Держит API-ключ на сервере, ограничивает частоту запросов и переключается
на запасного провайдера, если основной недоступен.

Запуск локально:
    pip install -r requirements.txt
    uvicorn main:app --host 0.0.0.0 --port 8000

Переменные окружения: см. .env.example
"""
import asyncio
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- основной провайдер ---
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "nvidia/nemotron-3.5-super-vl:free").strip()

# --- запасной провайдер (необязательно) ---
FALLBACK_BASE_URL = os.getenv("FALLBACK_BASE_URL", "").strip()
FALLBACK_API_KEY = os.getenv("FALLBACK_API_KEY", "").strip()
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "").strip()

# --- доступ и лимиты ---
APP_TOKEN = os.getenv("APP_TOKEN", "").strip()
RATE_PER_HOUR = int(os.getenv("RATE_PER_HOUR", "30"))
RATE_PER_DAY = int(os.getenv("RATE_PER_DAY", "200"))

# --- самопинг для Render ---
PING_URL = os.getenv("PING_URL", "").strip()
PING_INTERVAL = int(os.getenv("PING_INTERVAL", "600"))

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "Ты — сильный репетитор. Решай задачи пошагово: «Дано» → «Решение» → «Ответ». "
    "Формулы — обычным текстом (x², √(2), ∠ABC, ⊥, ∥, α, β, π), без LaTeX. "
    "Если данных не хватает — задай уточняющий вопрос. Отвечай на языке вопроса.",
).strip()


def _providers() -> list[tuple[str, str, str]]:
    out = [(LLM_BASE_URL, LLM_API_KEY, LLM_MODEL)]
    if FALLBACK_BASE_URL and FALLBACK_API_KEY and FALLBACK_MODEL:
        out.append((FALLBACK_BASE_URL, FALLBACK_API_KEY, FALLBACK_MODEL))
    return out


async def _keepalive() -> None:
    """Пингует сам себя, чтобы бесплатный Render не засыпал."""
    if not PING_URL:
        return
    while True:
        await asyncio.sleep(PING_INTERVAL)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.get(PING_URL)
        except Exception:  # noqa: BLE001
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_keepalive())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="ДЗ-Бот proxy", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatIn(BaseModel):
    messages: list[dict]
    model: str | None = None


# --- лимиты по устройству/IP ---
_buckets: dict[str, list[float]] = defaultdict(list)


def _client_key(request: Request) -> str:
    device = request.headers.get("X-Device-Id", "").strip()
    if device:
        return "d:" + device
    host = request.client.host if request.client else "unknown"
    return "ip:" + host


def _allow(key: str) -> tuple[bool, int]:
    """Возвращает (можно, сколько ещё осталось в этом часе)."""
    now = time.time()
    bucket = [t for t in _buckets[key] if now - t < 86400]
    hour = sum(1 for t in bucket if now - t < 3600)
    if hour >= RATE_PER_HOUR or len(bucket) >= RATE_PER_DAY:
        _buckets[key] = bucket
        return False, 0
    bucket.append(now)
    _buckets[key] = bucket
    return True, RATE_PER_HOUR - hour - 1


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "model": LLM_MODEL,
        "keepalive": bool(PING_URL),
        "limits": {"per_hour": RATE_PER_HOUR, "per_day": RATE_PER_DAY},
    }


@app.post("/api/chat")
async def chat(inp: ChatIn, request: Request) -> dict:
    if APP_TOKEN and request.headers.get("X-App-Token") != APP_TOKEN:
        raise HTTPException(status_code=401, detail="Неверный токен приложения")

    key = _client_key(request)
    allowed, left = _allow(key)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Слишком много запросов. Лимит: {RATE_PER_HOUR} в час, "
            f"{RATE_PER_DAY} в сутки. Попробуйте позже.",
        )

    messages = inp.messages
    if not messages or messages[0].get("role") != "system":
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    last_error = "нет провайдеров"
    for base, api_key, model in _providers():
        if not api_key:
            continue
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                r = await client.post(
                    base.rstrip("/") + "/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": inp.model or model,
                        "messages": messages,
                        "temperature": 0.5,
                    },
                )
        except Exception as e:  # noqa: BLE001
            last_error = f"{model}: {type(e).__name__}"
            continue

        if r.status_code != 200:
            last_error = f"{model}: HTTP {r.status_code} {r.text[:300]}"
            continue

        data = r.json()
        reply = (
            ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        ).strip()
        if reply:
            return {"reply": reply, "left": left}
        last_error = f"{model}: пустой ответ"

    raise HTTPException(status_code=502, detail=last_error)
