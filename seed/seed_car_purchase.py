"""Seed expanded keywords for car-purchase segment.

Context: user is a BUYER looking for SELLERS.
Demand = people SELLING cars (LEADS).
Stop = competing BUYERS also looking to buy (BLOCK).
Synonym = car/auto variations for classifier.
"""
import asyncio
import sys
sys.path.insert(0, '.')

from app.db.session import async_session_factory
from app.db.models import Segment, SegmentKeyword
from sqlalchemy import select, delete

CAR_PURCHASE_SLUG = "car-purchase"

DEMAND = [
    # ── RU: "продам/продаю" — sellers are LEADS ──
    "продам авто",
    "продам автомобиль",
    "продам машину",
    "продаю авто",
    "продаю автомобиль",
    "продаю машину",
    "срочно продам авто",
    "срочно продам машину",
    "продам авто срочно",
    "продам машину срочно",

    # ── RU: listing patterns ──
    "отдам авто",
    "отдам машину",
    "отдам автомобиль",
    "продаётся авто",
    "продаётся автомобиль",
    "продаётся машина",
    "авто на продажу",
    "автомобиль на продажу",
    "машина на продажу",

    # ── RU: condition / price / documents ──
    "продам авто с документами",
    "продам машину с документами",
    "продам авто в хорошем состоянии",
    "продам машину в отличном состоянии",
    "продам авто недорого",
    "продам машину недорого",
    "продам авто дёшево",
    "продам авто б/у",
    "продам машину б/у",
    "продам авто с пробегом",
    "продам машину с пробегом",
    "продам авто цена",
    "продам машину цена",
    "продам авто новое",
    "продам машину новую",

    # ── RU: body types ──
    "продам седан",
    "продам хэтчбек",
    "продам универсал",
    "продам кроссовер",
    "продам внедорожник",
    "продам джип",
    "продам пикап",
    "продам минивэн",
    "продам микроавтобус",
    "продам кабриолет",
    "продам купе",
    "продам грузовик",
    "продам фургон",
    "продам электромобиль",
    "продам гибрид",

    # ── RU: brands ──
    "продам тойоту",
    "продам хонду",
    "продам ниссан",
    "продам мазду",
    "продам бмв",
    "продам мерседес",
    "продам ауди",
    "продам фольксваген",
    "продам форд",
    "продам хендай",
    "продам киа",
    "продам шкоду",
    "продам рено",
    "продам пежо",
    "продам субару",
    "продам митсубиси",
    "продам лексус",
    "продам теслу",

    # ── RU: urgency / context ──
    "продам авто уезжаю",
    "продам машину переезд",
    "продам авто срочно уезжаю",
    "продам авто торг",
    "продам машину торг уместен",
    "продам авто возможен обмен",
    "продам машину или обменяю",
    "продам авто обмен",
    "продам авто в связи с отъездом",

    # ── EN ──
    "selling my car",
    "sell my car",
    "sell my vehicle",
    "car for sale",
    "auto for sale",
    "vehicle for sale",
    "used car for sale",
    "second hand car",
    "pre owned car",
    "car in good condition",
    "car with papers",
    "cheap car for sale",
    "must sell my car",
    "urgent sale car",
    "moving sale car",
    "toyota for sale",
    "honda for sale",
    "bmw for sale",
    "mercedes for sale",
]

STOP = [
    # ── RU: buyers = COMPETITORS ──
    "куплю авто",
    "куплю автомобиль",
    "куплю машину",
    "ищу авто",
    "ищу автомобиль",
    "ищу машину",
    "хочу купить авто",
    "хочу купить автомобиль",
    "хочу купить машину",
    "хочу авто",
    "хочу машину",
    "приобрету авто",
    "приобрету автомобиль",
    "приобрету машину",
    "рассмотрю авто",
    "рассмотрю машину",
    "интересует авто",
    "интересует автомобиль",
    "интересует машина",
    "ищу авто б/у",
    "ищу машину б/у",
    "ищу авто бэушное",
    "ищу машину бэушную",
    "ищу авто недорого",
    "ищу машину недорого",
    "ищу авто до",
    "ищу машину до",
    "посоветуйте где купить авто",
    "посоветуйте где купить машину",
    "где купить авто",
    "где купить машину",
    "ищу авто для покупки",
    "ищу машину для покупки",
    "хочу приобрести авто",
    "хочу приобрести автомобиль",
    "хочу приобрести машину",
    "нужен авто с документами",
    "нужна машина б/у",
    "нужен автомобиль до",
    "ищу подержанную машину",
    "куплю авто с пробегом",
    "куплю микроавтобус",
    "ищу машину на автомате",
    "ищу седан",
    "хочу купить джип",
    "хочу купить пикап",

    # ── EN: competing buyers ──
    "looking to buy a car",
    "want to buy a car",
    "looking for a used car",
    "looking for a cheap car",
    "need a second hand car",
    "wanted car",
    "buy car",
    "buy a car",
    "looking for car",
    "searching for a car",
    "looking for a vehicle",

    # ── RU: dealerships / resellers ──
    "автосалон",
    "автосалон предлагает",
    "продажа авто",
    "продажа автомобилей",
    "продажа машин",
    "автомобили в наличии",
    "машины в наличии",
    "авто в наличии",
    "предлагаем автомобили",
    "предлагаем авто",
    "предлагаю автомобиль",
    "авто с пробегом продажа",
    "трейд-ин",
    "trade-in авто",
]

SYNONYM = [
    # Vehicle synonyms
    "авто",
    "автомобиль",
    "машина",
    "тачка",
    "автомобильчик",
    # Condition
    "б/у",
    "подержанный",
    "бэушный",
    "с пробегом",
    # Actions
    "продам",
    "продаю",
    "продаётся",
    "отдам",
    "на продажу",
    "for sale",
    "selling",
    # Body types
    "седан",
    "хэтчбек",
    "универсал",
    "кроссовер",
    "внедорожник",
    "джип",
    "пикап",
    "минивэн",
    "микроавтобус",
    "кабриолет",
    "купе",
    "грузовик",
    "фургон",
    "электромобиль",
    "гибрид",
    # Brands
    "тойота",
    "хонда",
    "ниссан",
    "мазда",
    "бмв",
    "мерседес",
    "ауди",
    "фольксваген",
    "форд",
    "хендай",
    "киа",
    "шкода",
    "рено",
    "пежо",
    "субару",
    "митсубиси",
    "лексус",
    "тесла",
]


async def main():
    async with async_session_factory() as session:
        seg = (await session.execute(
            select(Segment).where(Segment.slug == CAR_PURCHASE_SLUG)
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
        print(f"Inserted {count} keywords: {len(DEMAND)} demand, {len(STOP)} stop, {len(SYNONYM)} synonym")


if __name__ == "__main__":
    asyncio.run(main())
