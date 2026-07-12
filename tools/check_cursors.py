"""One-shot cursor check script — run inside worker container, READ-ONLY.
Usage: docker compose exec worker python3 /app/check_cursors.py
Uses acc2 (SLEEPING) to avoid conflicts with active acc1 polling.
"""
import asyncio
from telethon import TelegramClient
from app.config import settings

CHANNELS = [
    ("side_forum", 175627),
    ("nha_trang_chat", 430),
    ("vietnam_muine_chat", 1552),
]


async def check(channel_username: str, cursor: int, client: TelegramClient):
    try:
        entity = await client.get_entity(channel_username)
        msgs = await client.get_messages(entity, limit=1)
        if msgs and len(msgs) > 0:
            msg = msgs[0]
            gap = cursor - msg.id if cursor > msg.id else 0
            verdict = (
                f"CURSOR ZAVYSHEN by {gap} msgs — poller пропускает новые"
                if cursor > msg.id
                else "OK (cursor <= last msg id)"
            )
            print(
                f"  {channel_username}: cursor={cursor} last_msg_id={msg.id} "
                f"last_date={msg.date} => {verdict}"
            )
        else:
            print(f"  {channel_username}: cursor={cursor} NO MESSAGES")
    except Exception as e:
        print(f"  {channel_username}: ERROR {type(e).__name__}: {e}")


async def main():
    api_id, api_hash, _ = settings.get_userbot_creds(2)
    client = TelegramClient("/app/sessions/userbot2", api_id, api_hash)

    print("Starting acc2 client (idle — acc2 is SLEEPING)...")
    await client.start()
    me = await client.get_me()
    print(f"Connected as: {me.first_name} (@{me.username})")

    for ch, cur in CHANNELS:
        await check(ch, cur, client)

    await client.disconnect()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
