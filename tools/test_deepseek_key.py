"""Test DeepSeek API key with a single real call.

Usage:
    docker compose exec worker python tools/test_deepseek_key.py

Prerequisites:
    DEEPSEEK_API_KEY=sk-...  in .env
"""

import asyncio
import json
import sys

import aiohttp


# Minimal test message — unambiguous commercial demand
TEST_MESSAGE = "ищу поставщика кофе в Нячанге"

# System prompt (abbreviated — just enough to get a valid response)
SYSTEM_PROMPT = """You classify messages from Vietnamese expat chats into:
DEMAND (commercial service/product search), OFFER (advertisement), OTHER.
Respond with JSON: {"category": "DEMAND"|"OFFER"|"OTHER", "reason": "..."}"""


async def main():
    from app.config import settings

    api_key = settings.deepseek_api_key
    model = settings.deepseek_model

    if not api_key or api_key.startswith("#"):
        print("❌ DEEPSEEK_API_KEY not set or is a comment placeholder.")
        print(f"   Current value: {repr(api_key[:30])}...")
        print("   Set DEEPSEEK_API_KEY=sk-... in .env and restart.")
        sys.exit(1)

    print(f"🔑 Key: {api_key[:10]}...{api_key[-4:]}")
    print(f"🤖 Model: {model}")
    print(f"📝 Test message: «{TEST_MESSAGE}»")
    print()

    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": TEST_MESSAGE},
        ],
        "temperature": 0.0,
        "max_tokens": 200,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                body = await resp.text()

                if resp.status != 200:
                    print(f"❌ API returned {resp.status}")
                    print(f"   Response: {body[:500]}")
                    if resp.status == 401:
                        print("   → API key is invalid or expired.")
                    elif resp.status == 404:
                        print("   → Model name not found. Check DEEPSEEK_MODEL.")
                    sys.exit(1)

                data = json.loads(body)
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})

                print("✅ API call successful!")
                print(f"   Tokens: {usage.get('total_tokens', '?')} "
                      f"(in={usage.get('prompt_tokens', '?')}, "
                      f"out={usage.get('completion_tokens', '?')})")
                print(f"   Response: {content[:300]}")

                # Validate: expect DEMAND
                if "DEMAND" in content.upper():
                    print("   ✅ Model correctly identified DEMAND.")
                    print("\n🎉 DeepSeek API is ready. Proceed with full prompt test.")
                else:
                    print(f"   ⚠️ Unexpected response. Expected DEMAND for this message.")
                    print(f"   Full response: {content}")

    except asyncio.TimeoutError:
        print("❌ Request timed out (15s). Check network connectivity.")
        sys.exit(1)
    except aiohttp.ClientError as e:
        print(f"❌ Network error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
