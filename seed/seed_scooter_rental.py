"""Seed expanded keywords for scooter-rental segment.

Context: user is a RENTAL SHOP OWNER looking for people who want to RENT.
Demand = people asking where/how to rent, looking for a bike/scooter.
Stop = rental shops advertising their fleet (competitors).
Synonym = alternative phrasings.
"""
import asyncio
import sys
sys.path.insert(0, '.')

from app.db.session import async_session_factory
from app.db.models import Segment, SegmentKeyword
from sqlalchemy import select, delete

SCOOTER_RENTAL_SLUG = "scooter-rental"

DEMAND = [
    # ── RU: direct "ищу/нужен/хочу + аренда/прокат" ──
    "ищу аренду скутера",
    "ищу скутер в аренду",
    "ищу байк в аренду",
    "ищу мотоцикл в аренду",
    "ищу мопед в аренду",
    "ищу прокат байков",
    "ищу прокат мотоциклов",
    "ищу прокат скутеров",
    "нужен скутер напрокат",
    "нужен байк напрокат",
    "нужен мотоцикл напрокат",
    "нужен мопед напрокат",
    "нужна аренда скутера",
    "нужна аренда мотоцикла",
    "нужна аренда байка",
    "хочу арендовать скутер",
    "хочу арендовать байк",
    "хочу арендовать мотоцикл",
    "хочу взять скутер напрокат",
    "хочу взять байк напрокат",
    "хочу взять мотобайк напрокат",
    "хочу мотоцикл в аренду",
    "возьму скутер в аренду",
    "возьму байк напрокат",
    "возьму скутер напрокат",
    "возьму мотоцикл в аренду",
    "сниму байк",
    "сниму скутер",
    "сниму мотоцикл",
    "сниму мопед",

    # ── RU: duration-specific ──
    "ищу байк на день",
    "ищу байк на неделю",
    "ищу байк на месяц",
    "ищу байк на пару дней",
    "ищу байк на 2 недели",
    "ищу байк на 1 день",
    "ищу байк на 3 дня",
    "ищу байк на сезон",
    "ищу байк на длительный срок",
    "ищу скутер на месяц",
    "ищу скутер на неделю",
    "нужен байк на месяц",
    "нужен байк на неделю",
    "нужен байк на 2 недели",
    "нужен байк срочно",
    "нужен скутер срочно",
    "ищу долгосрочную аренду байка",
    "ищу долгосрочную аренду скутера",

    # ── RU: question forms ──
    "где арендовать скутер",
    "где арендовать байк",
    "где взять байк",
    "где взять скутер",
    "где взять мотоцикл",
    "где арендовать мотоцикл",
    "кто сдаёт скутеры",
    "кто сдаёт байки",
    "кто сдаёт мотоциклы",
    "кто сдаёт байк",
    "кто сдаёт скутер",
    "кто сдаёт мотоцикл",
    "подскажите прокат мотоциклов",
    "подскажите прокат байков",
    "посоветуйте прокат скутеров",
    "посоветуйте прокат байков",
    "сколько стоит аренда скутера",
    "сколько стоит прокат байка",
    "сколько стоит аренда мотоцикла",
    "аренда скутера цена",
    "прокат байка цена",

    # ── RU: tourist/visitor context ──
    "приехал нужен байк",
    "приехал нужен скутер",
    "прилетел нужен байк",
    "приехали нужен транспорт",
    "турист нужен байк",
    "туристу нужен скутер",

    # ── EN ──
    "rent a scooter",
    "rent a motorbike",
    "rent a bike",
    "need a scooter",
    "need a motorbike",
    "need a bike",
    "need to rent a scooter",
    "need to rent a motorbike",
    "looking for bike rental",
    "looking for scooter rental",
    "looking for motorbike rental",
    "looking to rent a bike",
    "looking to rent a scooter",
    "looking to rent a motorbike",
    "where to rent a scooter",
    "where to rent a motorbike",
    "where to rent a bike",
    "where to hire a bike",
    "where to hire a scooter",
    "scooter rental near me",
    "motorbike rental near me",
    "bike rental near me",
    "scooter hire",
    "motorbike hire",
    "bike hire",
    "daily scooter rental",
    "weekly bike rental",
    "monthly bike rental",
    "long term scooter rental",
    "scooter for rent",
    "motorbike for rent",
    "bike for rent",
]

STOP = [
    # ── RU: rental shop advertising ──
    "сдаю скутер в аренду",
    "сдаю байк в аренду",
    "сдаю мотоцикл в аренду",
    "сдаём скутеры",
    "сдаём байки",
    "предлагаю прокат байков",
    "предлагаю прокат скутеров",
    "предлагаю аренду мотоциклов",
    "мотоциклы напрокат",
    "скутеры напрокат",
    "байки напрокат",
    "прокат скутеров",
    "прокат байков",
    "прокат мотоциклов",
    "аренда байков у нас",
    "аренда скутеров у нас",
    "скутеры в наличии",
    "байки в наличии",
    "свободные скутеры",
    "свободные байки",
    "бронируйте байк",
    "бронируйте скутер",
    "пишите в лс аренда",
    "звоните аренда байков",

    # ── EN ──
    "scooters for rent",
    "bikes for rent",
    "motorbikes for rent",
    "scooter rental service",
    "bike rental service",
    "we have scooters",
    "we rent bikes",
    "scooter rental business",
    "bike rental shop",
    "rent a scooter from us",
    "best scooter rental",
    "cheap scooter rental",
    "affordable bike rental",
]

SYNONYM = [
    # RU synonyms — help classifier match variations
    "аренда байка",
    "аренда мотоцикла",
    "аренда скутера",
    "аренда мопеда",
    "прокат байка",
    "прокат мотоцикла",
    "прокат скутера",
    "прокат мопеда",
    "байк напрокат",
    "скутер напрокат",
    "мотоцикл напрокат",
    "мопед напрокат",
    "взять байк",
    "взять скутер",
    "взять мотоцикл",
    "снять байк",
    "снять скутер",
    "снять мотоцикл",
    "мотобайк",
    "мотик",
    "посуточный прокат",
    "посуточная аренда",
]


async def main():
    async with async_session_factory() as session:
        seg = (await session.execute(
            select(Segment).where(Segment.slug == SCOOTER_RENTAL_SLUG)
        )).scalar_one()
        print(f"Segment: {seg.title_ru} (id={seg.id})")

        # Clear existing keywords for this segment
        deleted = (await session.execute(
            delete(SegmentKeyword).where(
                SegmentKeyword.segment_id == seg.id
            )
        )).rowcount
        print(f"Deleted {deleted} old keywords")

        # Insert new keywords
        count = 0
        for kw_type, words in [("demand", DEMAND), ("stop", STOP), ("synonym", SYNONYM)]:
            for text in words:
                session.add(SegmentKeyword(
                    segment_id=seg.id,
                    text=text,
                    keyword_type=kw_type,
                    is_active=True,
                ))
                count += 1

        await session.commit()
        print(f"Inserted {count} new keywords: {len(DEMAND)} demand, {len(STOP)} stop, {len(SYNONYM)} synonym")


if __name__ == "__main__":
    asyncio.run(main())
