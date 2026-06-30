"""Standalone script to authorize a Telethon userbot and save a session file.

Usage:
    python -m app.userbot.auth                    # authorize account 1 → sessions/userbot.session
    python -m app.userbot.auth --session userbot2  # authorize account 2 → sessions/userbot2.session

Environment (.env):
    Account 1: USERBOT_API_ID, USERBOT_API_HASH, USERBOT_PHONE
    Account 2: USERBOT_2_API_ID, USERBOT_2_API_HASH, USERBOT_2_PHONE
"""

import asyncio
import sys

from telethon import TelegramClient

from app.config import settings


def _resolve_creds(session_name: str) -> tuple[int, str, str]:
    """Map session name to (api_id, api_hash, phone) tuple."""
    if session_name in ("userbot", "userbot1"):
        return settings.get_userbot_creds(1)
    if session_name == "userbot2":
        api_id, api_hash, phone = settings.get_userbot_creds(2)
        if not api_id or not api_hash:
            print("ERROR: USERBOT_2_API_ID and USERBOT_2_API_HASH must be set in .env")
            sys.exit(1)
        if not phone:
            print("ERROR: USERBOT_2_PHONE must be set in .env")
            sys.exit(1)
        return (api_id, api_hash, phone)
    print(f"ERROR: Unknown session name '{session_name}'. Use 'userbot' or 'userbot2'.")
    sys.exit(1)


async def main():
    session_name = "userbot"
    if "--session" in sys.argv:
        idx = sys.argv.index("--session")
        if idx + 1 < len(sys.argv):
            session_name = sys.argv[idx + 1]

    api_id, api_hash, phone = _resolve_creds(session_name)

    client = TelegramClient(
        f"/app/sessions/{session_name}",
        api_id,
        api_hash,
    )
    await client.start(phone=phone or None)
    me = await client.get_me()
    print(f"Authorized as: {me.first_name} (@{me.username}) — phone: {me.phone}")
    print(f"Session saved to /app/sessions/{session_name}.session")


if __name__ == "__main__":
    asyncio.run(main())
