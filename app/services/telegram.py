"""
Telegram Bot Service — handles sending messages and bot operations.
"""
import httpx
from app.core.config import get_settings

settings = get_settings()

TELEGRAM_API = f"https://api.telegram.org/bot{settings.telegram_bot_token}"


class TelegramService:
    """Handles outbound Telegram operations."""

    def __init__(self):
        self.api_base = TELEGRAM_API

    async def send_message(self, chat_id: int, text: str, parse_mode: str = "Markdown") -> dict:
        """Send a message to a Telegram chat."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_base}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                },
            )
            return response.json()

    async def send_reply(self, chat_id: int, message_id: int, text: str) -> dict:
        """Reply to a specific message."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_base}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "reply_to_message_id": message_id,
                },
            )
            return response.json()

    async def set_webhook(self, url: str) -> dict:
        """Register the webhook URL with Telegram."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_base}/setWebhook",
                json={"url": url, "allowed_updates": ["message", "callback_query"]},
            )
            return response.json()

    async def get_me(self) -> dict:
        """Get bot info to verify the token works."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.api_base}/getMe")
            return response.json()


    async def send_message_with_inline_keyboard(
        self, chat_id: int, text: str, inline_keyboard: list,
        parse_mode: str = "Markdown"
    ) -> dict:
        """Send a message with inline keyboard buttons (e.g., snooze buttons)."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_base}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "reply_markup": {"inline_keyboard": inline_keyboard},
                },
            )
            return response.json()

    async def edit_message_reply_markup(
        self, chat_id: int, message_id: int, inline_keyboard: list = None
    ) -> dict:
        """Edit inline keyboard of an existing message (remove or update buttons)."""
        payload = {"chat_id": chat_id, "message_id": message_id}
        if inline_keyboard:
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
        else:
            payload["reply_markup"] = {"inline_keyboard": []}
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_base}/editMessageReplyMarkup",
                json=payload,
            )
            return response.json()

    async def answer_callback_query(
        self, callback_query_id: str, text: str = None
    ) -> dict:
        """Acknowledge an inline keyboard button press."""
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_base}/answerCallbackQuery",
                json=payload,
            )
            return response.json()


# Singleton
telegram_service = TelegramService()
