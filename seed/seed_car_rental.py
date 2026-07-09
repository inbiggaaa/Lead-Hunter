"""Seed expanded keywords for car-rental segment.

Context: user is a CAR RENTAL BUSINESS looking for people who want to RENT.
Demand = people asking where/how to rent, looking for a car.
Stop = competing rental companies advertising.
Synonym = alternative phrasings.
"""
import asyncio
import sys
sys.path.insert(0, '.')

from app.db.session import async_session_factory
from app.db.models import Segment, SegmentKeyword
from sqlalchemy import select, delete

CAR_RENTAL_SLUG = "car-rental"

DEMAND = [
    # ── RU: direct "ищу/нужен/хочу + аренда/прокат" ──
    "ищу аренду авто",
    "ищу аренду машины",
    "ищу авто в аренду",
    "ищу машину в аренду",
    "ищу машину напрокат",
    "ищу авто напрокат",
    "ищу автопрокат",
    "ищу прокат авто",
    "ищу прокат машин",
    "ищу каршеринг",
    "нужна машина в аренду",
    "нужна машина напрокат",
    "нужна аренда авто",
    "нужна аренда машины",
    "нужен автомобиль напрокат",
    "нужен автомобиль в аренду",
    "нужен автомобиль на время",
    "нужна аренда автомобиля",
    "хочу арендовать авто",
    "хочу арендовать машину",
    "хочу арендовать автомобиль",
    "хочу арендовать джип",
    "хочу арендовать внедорожник",
    "хочу арендовать минивэн",
    "хочу взять машину",
    "хочу взять авто",
    "возьму авто в аренду",
    "возьму машину в аренду",
    "возьму авто напрокат",
    "возьму машину напрокат",
    "сниму авто",
    "сниму машину",
    "сниму автомобиль",
    "арендую машину",
    "арендую авто",

    # ── RU: with driver ──
    "ищу авто с водителем",
    "ищу машину с водителем",
    "нужна машина с водителем",
    "нужен автомобиль с водителем",
    "ищу аренду авто с водителем",
    "нужен водитель на арендованной машине",

    # ── RU: duration-specific ──
    "нужна машина на сутки",
    "нужна машина на день",
    "нужна машина на неделю",
    "нужна машина на месяц",
    "нужна машина на несколько дней",
    "нужна машина на 1 день",
    "нужна машина на 2 недели",
    "нужна машина на 3 дня",
    "нужна машина на пару дней",
    "ищу авто на длительный срок",
    "ищу долгосрочную аренду авто",
    "ищу машину на длительный срок",
    "ищу аренду авто на месяц",
    "ищу машину на неделю",
    "ищу машину на месяц",
    "нужен автомобиль на неделю",
    "нужен автомобиль на месяц",

    # ── RU: question forms ──
    "где арендовать автомобиль",
    "где арендовать машину",
    "где арендовать авто",
    "где взять машину",
    "где взять авто",
    "где найти прокат машины",
    "кто сдаёт авто",
    "кто сдаёт машину",
    "кто сдаёт машины в аренду",
    "посоветуйте прокат авто",
    "посоветуйте прокат машин",
    "посоветуйте где взять машину",
    "подскажите аренду авто",
    "подскажите прокат авто",
    "подскажите аренду машины",
    "сколько стоит аренда авто",
    "сколько стоит прокат машины",
    "аренда авто цена",
    "прокат авто цена",

    # ── RU: special vehicles ──
    "хочу арендовать минивен",
    "нужен минивэн напрокат",
    "ищу внедорожник в аренду",
    "хочу арендовать микроавтобус",
    "нужен микроавтобус напрокат",
    "ищу джип в аренду",
    "хочу арендовать кабриолет",
    "ищу грузовой фургон в аренду",
    "нужен пикап напрокат",
    "аренда премиум авто",
    "хочу арендовать бизнес-класс",

    # ── RU: tourist/visitor ──
    "приехал нужна машина",
    "прилетел нужна машина",
    "туристу нужна машина",
    "турист нужен автомобиль",
    "приехали нужен транспорт",
    "в аэропорту нужна машина",

    # ── EN ──
    "rent a car",
    "rent a vehicle",
    "need a car",
    "need to rent a car",
    "need a car rental",
    "need a car hire",
    "looking for car rental",
    "looking for a rental car",
    "looking for car hire",
    "looking to rent a car",
    "where to rent a car",
    "where to hire a car",
    "car rental near me",
    "car hire near me",
    "car hire",
    "vehicle rental",
    "daily car rental",
    "weekly car rental",
    "monthly car rental",
    "long term car rental",
    "need a car for a week",
    "need a car for a month",
    "rent a car with driver",
    "car with driver",
    "hire car with driver",
    "self drive car rental",
    "rent a 4x4",
    "rent an SUV",
    "rent a minivan",
    "need a rental car",
]

STOP = [
    # ── RU: rental company advertising ──
    "сдаю авто в аренду",
    "сдаю машину в аренду",
    "сдаём авто",
    "сдаём машины",
    "предлагаю прокат машин",
    "предлагаю аренду авто",
    "предлагаем аренду автомобилей",
    "автопрокат работает",
    "автопрокат предлагает",
    "машины напрокат",
    "авто напрокат",
    "аренда автомобилей",
    "аренда авто у нас",
    "прокат авто",
    "прокат автомобилей",
    "авто в наличии",
    "машины в наличии",
    "свободные авто",
    "свободные машины",
    "бронируйте авто",
    "бронируйте машину",
    "пишите в лс аренда авто",
    "звоните прокат машин",
    "автопарк",
    "свой автопарк",
    "большой выбор авто",

    # ── EN ──
    "cars for rent",
    "car rental service",
    "car rental company",
    "we rent cars",
    "we have cars",
    "rent a car from us",
    "best car rental",
    "cheap car rental",
    "affordable car rental",
    "car rental business",
    "car rental agency",
    "luxury car rental",
    "premium car rental",
]

SYNONYM = [
    # RU synonyms
    "аренда авто",
    "аренда автомобиля",
    "аренда машины",
    "прокат авто",
    "прокат машин",
    "прокат автомобиля",
    "автопрокат",
    "машина напрокат",
    "авто напрокат",
    "автомобиль напрокат",
    "каршеринг",
    "взять машину",
    "взять авто",
    "снять машину",
    "снять авто",
    "посуточный прокат",
    "посуточная аренда",
    "автомобиль",
    "авто",
    "машина",
    "транспортное средство",
    "джип",
    "внедорожник",
    "минивэн",
    "микроавтобус",
    "седа́н",
    "кроссовер",
    "пикап",
    "кабриолет",
    "бизнес-класс",
    "премиум авто",
]


async def main():
    async with async_session_factory() as session:
        seg = (await session.execute(
            select(Segment).where(Segment.slug == CAR_RENTAL_SLUG)
        )).scalar_one()
        print(f"Segment: {seg.title_ru} (id={seg.id})")

        deleted = (await session.execute(
            delete(SegmentKeyword).where(SegmentKeyword.segment_id == seg.id)
        )).rowcount
        print(f"Deleted {deleted} old keywords")

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
