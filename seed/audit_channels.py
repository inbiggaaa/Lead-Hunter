"""Audit all catalog channels for accessibility via userbot."""

import asyncio
import sys
from pathlib import Path

from telethon import TelegramClient
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.db.session import async_session_factory
from app.db.models import CatalogChannel

OUTPUT = Path("/app/channel_audit.txt")


async def check_channel(client: TelegramClient, username: str) -> str:
    """Check if channel is accessible. Returns status string."""
    try:
        entity = await client.get_entity(username)
        # Get participant count if available
        participants = getattr(entity, 'participants_count', None)
        title = getattr(entity, 'title', '?')
        p_str = f" ({participants}👥)" if participants else ""
        return f"✅ {title}{p_str}"
    except Exception as e:
        err = str(e)
        if "private" in err.lower() or "ChannelPrivateError" in str(type(e)):
            return "🔒 PRIVATE"
        elif "banned" in err.lower():
            return "🚫 BANNED"
        elif "not found" in err.lower() or "not exist" in err.lower():
            return "❌ NOT FOUND"
        elif "flood" in err.lower():
            return "⏳ FLOOD WAIT"
        else:
            return f"⚠️ {err[:80]}"


async def main():
    print("Connecting to Telegram...")
    client = TelegramClient(
        str(Path("/app/sessions/userbot")),
        settings.userbot_api_id,
        settings.userbot_api_hash,
    )
    await client.start()

    async with async_session_factory() as session:
        result = await session.execute(
            select(CatalogChannel.chat_username, CatalogChannel.title)
            .order_by(CatalogChannel.chat_username)
        )
        channels = result.all()

    total = len(channels)
    print(f"Checking {total} channels...")
    results = {"ok": [], "private": [], "banned": [], "not_found": [], "error": []}

    report_lines = [
        f"# Channel Audit — {total} channels\n",
        f"Date: {__import__('datetime').datetime.now()}\n\n",
    ]

    for i, (username, title) in enumerate(channels):
        if i % 50 == 0:
            print(f"  Progress: {i}/{total}")

        status = await check_channel(client, username)
        line = f"{status} | @{username} | {title or ''}"

        if status.startswith("✅"):
            results["ok"].append(line)
        elif "PRIVATE" in status:
            results["private"].append(line)
        elif "BANNED" in status:
            results["banned"].append(line)
        elif "NOT FOUND" in status:
            results["not_found"].append(line)
        else:
            results["error"].append(line)

        await asyncio.sleep(0.15)  # Rate limit: ~7/sec

    # Build report
    report_lines.append(f"## ✅ Accessible: {len(results['ok'])}\n")
    for line in sorted(results["ok"]):
        report_lines.append(line + "\n")

    report_lines.append(f"\n## 🔒 Private: {len(results['private'])}\n")
    for line in sorted(results["private"]):
        report_lines.append(line + "\n")

    report_lines.append(f"\n## 🚫 Banned: {len(results['banned'])}\n")
    for line in sorted(results["banned"]):
        report_lines.append(line + "\n")

    report_lines.append(f"\n## ❌ Not Found: {len(results['not_found'])}\n")
    for line in sorted(results["not_found"]):
        report_lines.append(line + "\n")

    if results["error"]:
        report_lines.append(f"\n## ⚠️ Other Errors: {len(results['error'])}\n")
        for line in sorted(results["error"]):
            report_lines.append(line + "\n")

    # Summary
    report_lines.append(f"\n## Summary\n")
    report_lines.append(f"Total: {total}\n")
    report_lines.append(f"✅ Accessible: {len(results['ok'])} ({100*len(results['ok'])/total:.1f}%)\n")
    report_lines.append(f"🔒 Private: {len(results['private'])} ({100*len(results['private'])/total:.1f}%)\n")
    report_lines.append(f"🚫 Banned: {len(results['banned'])} ({100*len(results['banned'])/total:.1f}%)\n")
    report_lines.append(f"❌ Not Found: {len(results['not_found'])} ({100*len(results['not_found'])/total:.1f}%)\n")

    OUTPUT.write_text("".join(report_lines), encoding="utf-8")
    print(f"\nReport saved to {OUTPUT}")

    # Print summary
    print(f"\n{'='*50}")
    print(f"✅ Accessible: {len(results['ok'])}/{total} ({100*len(results['ok'])/total:.1f}%)")
    print(f"🔒 Private:    {len(results['private'])}/{total}")
    print(f"🚫 Banned:     {len(results['banned'])}/{total}")
    print(f"❌ Not Found:  {len(results['not_found'])}/{total}")
    print(f"{'='*50}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
