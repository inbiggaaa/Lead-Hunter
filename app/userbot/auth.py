"""Standalone script to authorize the Telethon userbot and save a session file.

Run inside the container:
    python -m app.userbot.auth
"""

import asyncio

from telethon import TelegramClient

from app.config import settings


async def main():
    client = TelegramClient(
        "/app/sessions/userbot",
        settings.userbot_api_id,
        settings.userbot_api_hash,
    )
    await client.start(phone=settings.userbot_phone)
    me = await client.get_me()
    print(f"Authorized as: {me.first_name} (@{me.username}) — phone: {me.phone}")
    print("Session saved to /app/sessions/userbot.session")


if __name__ == "__main__":
    asyncio.run(main())
