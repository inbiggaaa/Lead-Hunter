"""Seed database with catalog data: countries, cities, segments, and keywords.

Run inside the container:
    python seed/seed_catalog.py
"""

import asyncio
from sqlalchemy import select, delete

from app.db.session import engine, async_session_factory
from app.db.models import Country, City, Segment, SegmentKeyword

# ── Countries ──

COUNTRIES = [
    {"slug": "vn", "name_ru": "Вьетнам", "name_en": "Vietnam"},
    {"slug": "id", "name_ru": "Индонезия", "name_en": "Indonesia"},
    {"slug": "th", "name_ru": "Таиланд", "name_en": "Thailand"},
    {"slug": "ru", "name_ru": "Россия", "name_en": "Russia"},
    {"slug": "other", "name_ru": "Другие страны", "name_en": "Other countries"},
]

# ── Cities ──

CITIES = {
    "vn": [
        {"slug": "nha-trang", "name_ru": "Нячанг", "name_en": "Nha Trang"},
        {"slug": "da-nang", "name_ru": "Дананг", "name_en": "Da Nang"},
        {"slug": "ho-chi-minh", "name_ru": "Хошимин", "name_en": "Ho Chi Minh"},
        {"slug": "hanoi", "name_ru": "Ханой", "name_en": "Hanoi"},
        {"slug": "phu-quoc", "name_ru": "Фукуок", "name_en": "Phu Quoc"},
        {"slug": "mui-ne", "name_ru": "Муйне", "name_en": "Mui Ne"},
    ],
    "id": [
        {"slug": "bali", "name_ru": "Бали", "name_en": "Bali"},
        {"slug": "jakarta", "name_ru": "Джакарта", "name_en": "Jakarta"},
        {"slug": "lombok", "name_ru": "Ломбок", "name_en": "Lombok"},
    ],
    "th": [
        {"slug": "bangkok", "name_ru": "Бангкок", "name_en": "Bangkok"},
        {"slug": "phuket", "name_ru": "Пхукет", "name_en": "Phuket"},
        {"slug": "pattaya", "name_ru": "Паттайя", "name_en": "Pattaya"},
        {"slug": "koh-samui", "name_ru": "Самуи", "name_en": "Koh Samui"},
        {"slug": "chiang-mai", "name_ru": "Чиангмай", "name_en": "Chiang Mai"},
    ],
    "ru": [
        {"slug": "moscow", "name_ru": "Москва", "name_en": "Moscow"},
        {"slug": "spb", "name_ru": "Санкт-Петербург", "name_en": "St. Petersburg"},
        {"slug": "sochi", "name_ru": "Сочи", "name_en": "Sochi"},
    ],
}

# ── Segments (abbreviated, full list in segment_seed.md) ──

SEGMENTS = [
    {"slug": "catering", "emoji": "🍜", "title_ru": "Кейтеринг / Повара", "title_en": "Catering / Chefs", "sort": 1},
    {"slug": "massage", "emoji": "💆", "title_ru": "Массаж", "title_en": "Massage", "sort": 2},
    {"slug": "bike-rental", "emoji": "🛵", "title_ru": "Аренда байков", "title_en": "Bike rental", "sort": 3},
    {"slug": "moto-purchase", "emoji": "🏍", "title_ru": "Покупка мотоцикла", "title_en": "Motorcycle purchase", "sort": 4},
    {"slug": "car-rental", "emoji": "🚗", "title_ru": "Аренда авто", "title_en": "Car rental", "sort": 5},
    {"slug": "cleaning", "emoji": "🧹", "title_ru": "Клининг", "title_en": "Cleaning", "sort": 6},
    {"slug": "beauty", "emoji": "💅", "title_ru": "Красота и уход", "title_en": "Beauty & care", "sort": 7},
    {"slug": "real-estate-rent", "emoji": "🏠", "title_ru": "Аренда жилья", "title_en": "Rental housing", "sort": 8},
    {"slug": "real-estate-buy", "emoji": "🏡", "title_ru": "Покупка жилья", "title_en": "Buying housing", "sort": 9},
    {"slug": "job-hiring", "emoji": "💼", "title_ru": "Работа (вакансии)", "title_en": "Jobs (hiring)", "sort": 10},
    {"slug": "job-seeking", "emoji": "🔎", "title_ru": "Работа (соискатели)", "title_en": "Jobs (seeking)", "sort": 11},
    {"slug": "tattoo", "emoji": "🎨", "title_ru": "Тату / Татуировки", "title_en": "Tattoo", "sort": 12},
    {"slug": "tourism", "emoji": "✈️", "title_ru": "Туризм / Экскурсии", "title_en": "Tourism / Excursions", "sort": 13},
    {"slug": "visa", "emoji": "📄", "title_ru": "Визы и документы", "title_en": "Visas & documents", "sort": 14},
    {"slug": "translation", "emoji": "🗣", "title_ru": "Переводчики", "title_en": "Translation", "sort": 15},
    {"slug": "repair", "emoji": "🔧", "title_ru": "Ремонт / Мастера", "title_en": "Repair / Handyman", "sort": 16},
    {"slug": "photo-video", "emoji": "📸", "title_ru": "Фото / Видео", "title_en": "Photo / Video", "sort": 17},
    {"slug": "fitness", "emoji": "💪", "title_ru": "Фитнес и спорт", "title_en": "Fitness & sport", "sort": 18},
    {"slug": "pets", "emoji": "🐾", "title_ru": "Услуги для животных", "title_en": "Pet services", "sort": 19},
    {"slug": "education", "emoji": "📚", "title_ru": "Обучение / Репетиторы", "title_en": "Education / Tutors", "sort": 20},
    {"slug": "medical", "emoji": "🏥", "title_ru": "Медицина / Врачи", "title_en": "Medical / Doctors", "sort": 21},
    {"slug": "legal", "emoji": "⚖️", "title_ru": "Юридические услуги", "title_en": "Legal services", "sort": 22},
    {"slug": "it-services", "emoji": "💻", "title_ru": "IT-услуги", "title_en": "IT services", "sort": 23},
    {"slug": "design", "emoji": "🎨", "title_ru": "Дизайн / Креатив", "title_en": "Design / Creative", "sort": 24},
    {"slug": "logistics", "emoji": "🚚", "title_ru": "Логистика / Доставка", "title_en": "Logistics / Delivery", "sort": 25},
    {"slug": "childcare", "emoji": "👶", "title_ru": "Няни / Присмотр за детьми", "title_en": "Nannies / Childcare", "sort": 26},
    {"slug": "events", "emoji": "🎉", "title_ru": "Организация мероприятий", "title_en": "Event planning", "sort": 27},
    {"slug": "crypto", "emoji": "₿", "title_ru": "Крипто / Обмен валют", "title_en": "Crypto / Currency exchange", "sort": 28},
    {"slug": "other-services", "emoji": "📌", "title_ru": "Другие услуги", "title_en": "Other services", "sort": 29},
]

# ── Keywords per segment (abbreviated; full set in segment_seed.md) ──

SEGMENT_KEYWORDS = {
    "catering": {
        "demand": [
            "ищу повара", "нужен повар", "ищу повора", "ищу шеф-повара",
            "нужен шеф", "нужен кейтеринг", "заказать кейтеринг",
            "ищу кейтеринг", "нужна кухня", "нужен кухонный работник",
            "ищу повара на дом", "нужен повар на дом",
            "looking for a chef", "need a chef", "need a cook",
            "looking for catering", "need catering", "hire a chef",
        ],
        "stop": [
            "работаю поваром", "я повар", "предлагаю кейтеринг",
            "chef available", "catering services",
        ],
    },
    "massage": {
        "demand": [
            "ищу массажиста", "нужен массаж", "нужен массажист",
            "посоветуйте массаж", "где массаж", "хочу массаж",
            "ищу мастера массажа", "ищу спа", "нужен спа",
            "looking for massage", "need a massage", "where to get massage",
        ],
        "stop": [
            "делаю массаж", "массажист с опытом", "предлагаю массаж",
            "massage available", "massage therapist",
        ],
    },
    "bike-rental": {
        "demand": [
            "ищу байк в аренду", "нужен байк в аренду", "сниму байк",
            "аренда байка", "ищу скутер в аренду", "нужен скутер напрокат",
            "хочу арендовать байк", "возьму байк напрокат",
            "looking for bike rental", "need a bike", "rent a scooter",
            "rent a motorbike", "where to rent a scooter",
        ],
        "stop": [
            "сдаю байк", "сдаю скутер", "bike for rent", "scooter for rent",
        ],
    },
    "cleaning": {
        "demand": [
            "ищу уборщицу", "нужна уборка", "нужен клининг",
            "ищу клининг", "хочу уборку", "заказать уборку",
            "нужна домработница", "ищу домработницу",
            "looking for cleaning", "need a cleaner", "need cleaning service",
        ],
        "stop": [
            "предлагаю уборку", "cleaning services", "cleaner available",
        ],
    },
    "beauty": {
        "demand": [
            "ищу мастера маникюра", "нужен маникюр", "ищу бровиста",
            "ищу косметолога", "нужен парикмахер", "где подстричься",
            "ищу мастера по волосам", "нужен колорист",
            "looking for nail tech", "need a haircut", "need a hairdresser",
        ],
        "stop": [
            "делаю маникюр", "принимаю клиентов", "beauty salon",
        ],
    },
}


async def seed():
    async with async_session_factory() as session:
        # Clear existing seed data (preserve users)
        for model in [SegmentKeyword, City, Country, Segment]:
            await session.execute(delete(model))

        # Countries
        country_map: dict[str, Country] = {}
        for c in COUNTRIES:
            obj = Country(**c)
            session.add(obj)
            country_map[c["slug"]] = obj
        await session.flush()

        # Cities
        for country_slug, city_list in CITIES.items():
            country = country_map.get(country_slug)
            if not country:
                continue
            for city_data in city_list:
                session.add(City(**city_data, country_id=country.id))
        await session.flush()

        # Segments
        segment_map: dict[str, Segment] = {}
        for seg in SEGMENTS:
            obj = Segment(
                slug=seg["slug"],
                title_ru=seg["title_ru"],
                title_en=seg["title_en"],
                emoji=seg["emoji"],
                sort_order=seg["sort"],
            )
            session.add(obj)
            segment_map[seg["slug"]] = obj
        await session.flush()

        # Segment keywords
        for slug, kw_data in SEGMENT_KEYWORDS.items():
            segment = segment_map.get(slug)
            if not segment:
                continue
            for kw_type in ("demand", "stop", "synonym"):
                for text in kw_data.get(kw_type, []):
                    session.add(
                        SegmentKeyword(
                            segment_id=segment.id,
                            text=text,
                            keyword_type=kw_type,
                        )
                    )

        await session.commit()
        print("Seed complete!")


if __name__ == "__main__":
    asyncio.run(seed())
