"""Seed universal stop-words into the database.

Inserts the UNIVERSAL_STOP list (previously hardcoded in classifier.py) as
segment_keywords records with segment_id=NULL and keyword_type='stop'.

Safe to run multiple times — skips already existing entries.
"""

import asyncio
from app.db.session import async_session_factory
from app.db.models import SegmentKeyword
from sqlalchemy import select, and_

# The full list from the old UNIVERSAL_STOP in classifier.py
UNIVERSAL_STOP_PHRASES = [
    # Booking/scheduling (offer)
    "записывайтесь", "запись открыта", "открыта запись", "свободные окошки",
    "свободно окошко", "есть окошко", "бронируйте", "по записи",
    # Self-promotion
    "прайс", "прайс-лист", "портфолио", "мастер с опытом", "работаю на дому",
    "принимаю у себя", "наш салон", "наша студия", "приглашаем вас",
    "у нас работают", "мы принимаем", "мы работаем", "мы предлагаем",
    "предлагаем услуги", "наши услуги", "записывайтесь к нам", "ждём вас",
    "приходите к нам", "мы открылись", "открылись", "новое место",
    "мы работаем по адресу", "наш адрес", "скидка сегодня", "акция сегодня",
    "спецпредложение",
    # Contact bait
    "пишите нам", "звоните нам", "подписывайтесь", "подписывайтесь на нас",
    "link in bio", "see our profile", "follow us", "ссылка в шапке",
    "ссылка в профиле", "ссылка в описании",
    # Price-first (offer signal)
    "цена от", "стоимость от", "цена указана", "цены в профиле",
    "доступные цены", "лучшие цены",
    # Already resolved
    "уже нашла", "уже нашёл", "уже записался", "уже записалась",
    "нашла мастера", "нашёл мастера", "вопрос решён", "уже не актуально",
    "спасибо всем", "нашли", "решила сама", "решил сам",
    "вопрос закрыт", "сделано",
    # Recommendation (past tense)
    "советую", "рекомендую", "был у", "была у", "ходил к", "ходила к",
    "попробовала", "попробовал", "понравилось", "не понравилось",
    "отличный мастер", "довольна результатом",
    # Urgency bait (offer)
    "места ещё есть", "осталось мало мест", "только сегодня", "только сейчас",
    "последние места", "акция действует", "набор закрыт",
    # English
    "book now", "slots available", "price list", "taking clients",
    "open for booking", "dm for price", "promotion today", "special offer",
    "discount today", "check out our", "visit us", "contact us",
    "hurry up", "limited time",
]


async def seed_universal_stops():
    """Insert universal stop-words, skipping duplicates."""
    inserted = 0
    skipped = 0

    async with async_session_factory() as session:
        for phrase in UNIVERSAL_STOP_PHRASES:
            # Check if already exists
            existing = await session.execute(
                select(SegmentKeyword).where(
                    and_(
                        SegmentKeyword.segment_id.is_(None),
                        SegmentKeyword.text == phrase,
                        SegmentKeyword.keyword_type == "stop",
                    )
                )
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            session.add(SegmentKeyword(
                segment_id=None,
                text=phrase,
                keyword_type="stop",
                is_regex=False,
                is_active=True,
            ))
            inserted += 1

        await session.commit()

    print(f"Universal stop-words: {inserted} inserted, {skipped} skipped (already exist)")


if __name__ == "__main__":
    asyncio.run(seed_universal_stops())
