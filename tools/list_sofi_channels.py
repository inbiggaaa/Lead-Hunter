"""List all channels accessible to @mill_sofi (account 2)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telethon import TelegramClient
from app.config import settings

SESSIONS_DIR = "/app/sessions"


async def main():
    api_id, api_hash, phone = settings.get_userbot_creds(2)
    
    client = TelegramClient(
        str(os.path.join(SESSIONS_DIR, "userbot2")),
        api_id,
        api_hash,
    )
    
    await client.start(phone=phone or None)
    me = await client.get_me()
    print(f"Connected as: @{me.username} (ID: {me.id})\n")
    
    channels = []
    private_channels = []
    
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        is_channel = getattr(entity, 'broadcast', False)
        if not is_channel:
            continue
        
        username = getattr(entity, 'username', None) or ''
        title = getattr(entity, 'title', '')
        entity_id = getattr(entity, 'id', 0)
        participants = getattr(entity, 'participants_count', None)
        is_private = not username
        
        ch = {
            'id': entity_id,
            'username': username,
            'title': title,
            'is_private': is_private,
            'participants': participants,
        }
        channels.append(ch)
        
        if is_private:
            private_channels.append(ch)
    
    # Print all channels
    print(f"{'#':<4} {'Private?':<9} {'Username':<35} {'Title':<50} {'Parts'}")
    print("-" * 110)
    for i, ch in enumerate(channels, 1):
        priv = "PRIVATE" if ch['is_private'] else "public"
        un = f"@{ch['username']}" if ch['username'] else "(no username)"
        parts = str(ch['participants']) if ch['participants'] else "?"
        print(f"{i:<4} {priv:<9} {un:<35} {ch['title'][:48]:<50} {parts}")
    
    print(f"\n---\nTotal: {len(channels)} channels ({len(private_channels)} private)")
    
    if private_channels:
        print("\n=== PRIVATE CHANNELS (need geo-categorization) ===")
        for i, ch in enumerate(private_channels, 1):
            parts = f"{ch['participants']} participants" if ch['participants'] else "unknown size"
            print(f"  {i}. {ch['title']} (id={ch['id']}, {parts})")
    
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
