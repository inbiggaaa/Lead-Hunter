"""Seed expanded keywords for moto-purchase segment.

Context: user is a BUYER looking for SELLERS.
Demand = people SELLING bikes/scooters (LEADS).
Stop = competing BUYERS also looking to buy (BLOCK).
Synonym = bike/scooter variations for classifier.
"""
import asyncio
import sys
sys.path.insert(0, '.')

from app.db.session import async_session_factory
from app.db.models import Segment, SegmentKeyword
from sqlalchemy import select, delete

MOTO_PURCHASE_SLUG = "moto-purchase"

DEMAND = [
    # ── RU: "продам/продаю" — sellers are LEADS ──
    "продам байк",
    "продам мотоцикл",
    "продам скутер",
    "продам мопед",
    "продам мото",
    "продам мотик",
    "продаю байк",
    "продаю мотоцикл",
    "продаю скутер",
    "продаю мопед",
    "продаю мото",
    "продаю мотик",
    "продам мотобайк",
    "продаю мотобайк",
    "срочно продам байк",
    "срочно продам мотоцикл",
    "срочно продам скутер",
    "продам байк срочно",
    "продам мотоцикл срочно",
    "продам скутер срочно",

    # ── RU: offer/listing patterns ──
    "отдам байк",
    "отдам мотоцикл",
    "отдам скутер",
    "отдам мото",
    "продаётся байк",
    "продаётся мотоцикл",
    "продаётся скутер",
    "продаётся мопед",
    "байк на продажу",
    "мотоцикл на продажу",
    "скутер на продажу",
    "мопед на продажу",
    "мото на продажу",

    # ── RU: price + document signals ──
    "продам байк документы",
    "продам мотоцикл с документами",
    "продам скутер с документами",
    "продам байк в хорошем состоянии",
    "продам мотоцикл в отличном состоянии",
    "продам скутер новый",
    "продам байк недорого",
    "продам мотоцикл недорого",
    "продам скутер недорого",
    "продам байк дёшево",
    "продам мотоцикл б/у",
    "продам скутер б/у",
    "продам байк с пробегом",
    "продам мотоцикл с пробегом",
    "продам скутер с пробегом",
    "продам байк цена",
    "продам мотоцикл цена",
    "продам скутер цена",

    # ── RU: specific brands / types ──
    "продам хонду",
    "продам ямаху",
    "продам сузуки",
    "продам кавасаки",
    "продам бмв мотоцикл",
    "продам дукати",
    "продам харлей",
    "продам спортбайк",
    "продам чоппер",
    "продам круизер",
    "продам эндуро",
    "продам кроссовый мотоцикл",
    "продам питбайк",
    "продам электроскутер",
    "продам электробайк",
    "продам трицикл",

    # ── RU: urgency / moving away ──
    "продам байк уезжаю",
    "продам мотоцикл переезд",
    "продам скутер срочно уезжаю",
    "продам байк торг",
    "продам мотоцикл торг уместен",
    "продам скутер возможен обмен",
    "продам байк или обменяю",
    "продам мотоцикл обмен",

    # ── EN ──
    "selling my bike",
    "selling my motorcycle",
    "selling my scooter",
    "sell my bike",
    "sell my scooter",
    "sell my motorbike",
    "bike for sale",
    "motorcycle for sale",
    "scooter for sale",
    "motorbike for sale",
    "moped for sale",
    "used bike for sale",
    "used scooter for sale",
    "second hand motorcycle",
    "used motorbike",
    "pre owned motorcycle",
    "bike in good condition",
    "bike with documents",
    "bike with papers",
    "cheap bike for sale",
    "must sell my bike",
    "urgent sale motorcycle",
    "moving sale bike",
    "honda for sale",
    "yamaha for sale",
]

STOP = [
    # ── RU: buyers = COMPETITORS (block) ──
    "куплю байк",
    "куплю мотоцикл",
    "куплю скутер",
    "куплю мопед",
    "куплю мото",
    "куплю мотик",
    "куплю мотобайк",
    "ищу байк",
    "ищу мотоцикл",
    "ищу скутер",
    "ищу мопед",
    "ищу мото",
    "хочу купить байк",
    "хочу купить мотоцикл",
    "хочу купить скутер",
    "хочу купить мопед",
    "хочу мотоцикл",
    "хочу байк",
    "хочу скутер",
    "хочу мотик",
    "хочу мото",
    "приобрету байк",
    "приобрету мотоцикл",
    "приобрету скутер",
    "рассмотрю байк",
    "рассмотрю мотоцикл",
    "рассмотрю скутер",
    "интересует байк",
    "интересует мотоцикл",
    "интересует скутер",
    "ищу байк б/у",
    "ищу скутер б/у",
    "ищу мотоцикл б/у",
    "ищу байк бэушный",
    "ищу скутер бэушный",
    "ищу байк недорого",
    "ищу скутер недорого",
    "ищу мотоцикл недорого",
    "ищу байк до",
    "ищу мотоцикл до",
    "ищу скутер до",
    "посоветуйте где купить байк",
    "посоветуйте где купить мотоцикл",
    "посоветуйте где купить скутер",
    "где купить байк",
    "где купить мотоцикл",
    "где купить скутер",
    "ищу байк для покупки",
    "ищу мотоцикл для покупки",
    "хочу приобрести байк",
    "хочу приобрести мотоцикл",
    "хочу приобрести скутер",
    "хочу взять байк в собственность",
    "ищу спортбайк",
    "ищу чоппер",
    "нужен круизер",
    "нужен эндуро",
    "нужен мотоцикл до 250 кубов",

    # ── EN: competing buyers ──
    "looking to buy a bike",
    "looking to buy a motorcycle",
    "looking to buy a scooter",
    "want to buy a bike",
    "want to buy a motorcycle",
    "want to buy a scooter",
    "looking for a used scooter",
    "looking for a used bike",
    "need a second hand bike",
    "looking for a cheap bike",
    "wanted motorcycle",
    "wanted scooter",
    "buy motorcycle",
    "buy a bike",
    "buy scooter",
    "looking for bike",
    "looking for scooter",
    "looking for motorcycle",
    "searching for a bike",
    "searching for a scooter",

    # ── RU: dealerships / resellers (not individuals) ──
    "мотосалон",
    "мотосалон предлагает",
    "продажа мотоциклов",
    "продажа байков",
    "продажа скутеров",
    "магазин мототехники",
    "предлагаем мотоциклы",
    "предлагаем байки",
    "предлагаю мототехнику",
    "мотоциклы в наличии",
    "байки в наличии",
]

SYNONYM = [
    # Vehicle type synonyms
    "байк",
    "мотоцикл",
    "скутер",
    "мопед",
    "мото",
    "мотик",
    "мотобайк",
    # Condition synonyms
    "б/у",
    "подержанный",
    "бэушный",
    "с пробегом",
    # Action synonyms
    "продам",
    "продаю",
    "продаётся",
    "отдам",
    "на продажу",
    "for sale",
    "selling",
    # Brand names (help match brand-specific listings)
    "хонда",
    "ямаха",
    "сузуки",
    "кавасаки",
    "бмв",
    "дукати",
    "харлей",
    "спортбайк",
    "чоппер",
    "круизер",
    "эндуро",
    "питбайк",
    "электроскутер",
    "электробайк",
    "трицикл",
]


async def main():
    async with async_session_factory() as session:
        seg = (await session.execute(
            select(Segment).where(Segment.slug == MOTO_PURCHASE_SLUG)
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
        print(f"Inserted {count} keywords: {len(DEMAND)} demand (sellers=leads), {len(STOP)} stop (buyers=competitors), {len(SYNONYM)} synonym")


if __name__ == "__main__":
    asyncio.run(main())
