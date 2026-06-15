import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger("ai-investor.telegram")

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_last_network_error_log = 0.0
_network_error_log_interval = 60.0


def is_configured() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_bot_username)


def api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"


def _client() -> httpx.Client:
    kwargs: dict = {"timeout": _TIMEOUT}
    if settings.telegram_proxy_url:
        kwargs["proxy"] = settings.telegram_proxy_url
    return httpx.Client(**kwargs)


def _log_network_error(method: str, exc: Exception) -> None:
    global _last_network_error_log
    now = time.monotonic()
    if now - _last_network_error_log >= _network_error_log_interval:
        _last_network_error_log = now
        hint = ""
        if not settings.telegram_proxy_url:
            hint = " (set TELEGRAM_PROXY_URL if api.telegram.org is blocked)"
        logger.warning("Telegram %s: %s%s", method, exc, hint)


def _api_post(method: str, json: dict | None = None) -> dict | None:
    if not settings.telegram_bot_token:
        return None
    try:
        with _client() as client:
            response = client.post(api_url(method), json=json or {})
            data = response.json()
            if not data.get("ok"):
                logger.error("Telegram %s failed: %s", method, data.get("description"))
            return data
    except httpx.HTTPError as exc:
        _log_network_error(method, exc)
        return None


def _api_get(method: str, params: dict | None = None) -> dict | None:
    if not settings.telegram_bot_token:
        return None
    try:
        with _client() as client:
            response = client.get(api_url(method), params=params or {})
            data = response.json()
            if not data.get("ok"):
                logger.error("Telegram %s failed: %s", method, data.get("description"))
            return data
    except httpx.HTTPError as exc:
        _log_network_error(method, exc)
        return {"ok": False, "description": str(exc)}


def delete_webhook() -> bool:
    data = _api_post("deleteWebhook", {"drop_pending_updates": True})
    if data and data.get("ok"):
        logger.info("Telegram webhook removed, polling enabled")
        return True
    return False


def set_bot_commands() -> bool:
    commands = [
        {"command": "start", "description": "Начать / подключить аккаунт"},
        {"command": "analyze", "description": "AI-анализ акции (например /analyze NVDA)"},
        {"command": "portfolio", "description": "Мой портфель"},
    ]
    data = _api_post("setMyCommands", {"commands": commands})
    return bool(data and data.get("ok"))


def send_message(chat_id: int, text: str) -> bool:
    if len(text) > 4096:
        text = text[:4093] + "..."
    data = _api_post(
        "sendMessage",
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
    )
    return bool(data and data.get("ok"))


def get_updates(offset: int | None = None) -> list[dict]:
    params: dict = {"timeout": 0, "allowed_updates": ["message"]}
    if offset is not None:
        params["offset"] = offset
    data = _api_get("getUpdates", params)
    if not data or not data.get("ok"):
        return []
    return data.get("result", [])
