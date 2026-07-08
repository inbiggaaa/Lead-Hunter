"""Seed database with catalog data: countries, cities, categories, segments, and keywords.

Run inside the container:
    python seed/seed_catalog.py
    python seed/seed_full_keywords.py  # after seeding structure, load keywords
"""

import asyncio
from sqlalchemy import select, delete

from app.db.session import engine, async_session_factory
from app.db.models import Country, City, Category, Segment, SegmentKeyword

# ── Countries ──

COUNTRIES = [
    {"slug": "vn", "name_ru": "Вьетнам", "name_en": "Vietnam"},
    {"slug": "id", "name_ru": "Индонезия", "name_en": "Indonesia"},
    {"slug": "th", "name_ru": "Таиланд", "name_en": "Thailand"},
    {"slug": "ph", "name_ru": "Филиппины", "name_en": "Philippines"},
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
    "ph": [
        {"slug": "manila", "name_ru": "Манила", "name_en": "Manila"},
        {"slug": "cebu", "name_ru": "Себу", "name_en": "Cebu"},
    ],
}

# ── Categories (16) ──

CATEGORIES = [
    {"slug": "transport",      "emoji": "🚗", "title_ru": "Транспорт",               "title_en": "Transport",              "sort": 1},
    {"slug": "logistics",      "emoji": "📦", "title_ru": "Логистика",               "title_en": "Logistics",              "sort": 2},
    {"slug": "real-estate",    "emoji": "🏠", "title_ru": "Недвижимость",            "title_en": "Real Estate",            "sort": 3},
    {"slug": "beauty",         "emoji": "💆", "title_ru": "Красота и уход",          "title_en": "Beauty & Care",          "sort": 4},
    {"slug": "doctor",         "emoji": "🩺", "title_ru": "Врач",                    "title_en": "Doctor",                 "sort": 5},
    {"slug": "translator",     "emoji": "🗣️", "title_ru": "Переводчик",              "title_en": "Translator",             "sort": 6},
    {"slug": "education",      "emoji": "📚", "title_ru": "Обучение и курсы",        "title_en": "Education & Courses",    "sort": 7},
    {"slug": "home",           "emoji": "🧹", "title_ru": "Дом и быт",               "title_en": "Home & Household",       "sort": 8},
    {"slug": "tourism",        "emoji": "✈️", "title_ru": "Туризм",                  "title_en": "Tourism",                "sort": 9},
    {"slug": "catering",       "emoji": "🍽️", "title_ru": "Кейтеринг и мероприятия", "title_en": "Catering & Events",      "sort": 10},
    {"slug": "fitness",        "emoji": "🏋️", "title_ru": "Фитнес и спорт",          "title_en": "Fitness & Sports",       "sort": 11},
    {"slug": "media-design",   "emoji": "📸", "title_ru": "Медиа и дизайн",          "title_en": "Media & Design",         "sort": 12},
    {"slug": "legal",          "emoji": "⚖️", "title_ru": "Консультация и Право",    "title_en": "Legal & Consulting",     "sort": 13},
    {"slug": "finance",        "emoji": "💰", "title_ru": "Финансы",                 "title_en": "Finance",                "sort": 14},
]

# ── Segments (66 subcategories grouped by category slug) ──

SEGMENTS_BY_CATEGORY = {
    "transport": [
        {"slug": "scooter-rental",   "emoji": "🛵", "title_ru": "Аренда скутеров и мотоциклов", "title_en": "Scooter & motorcycle rental", "sort": 1},
        {"slug": "car-rental",       "emoji": "🚙", "title_ru": "Аренда автомобиля",            "title_en": "Car rental",                   "sort": 2},
        {"slug": "moto-purchase",    "emoji": "🏍️", "title_ru": "Покупка мотоцикла",             "title_en": "Motorcycle purchase",          "sort": 3},
        {"slug": "car-purchase",     "emoji": "🚘", "title_ru": "Покупка авто",                 "title_en": "Car purchase",                 "sort": 4},
    ],
    "logistics": [
        {"slug": "delivery",         "emoji": "🚚", "title_ru": "Доставка",                     "title_en": "Delivery",                     "sort": 1},
        {"slug": "courier",          "emoji": "🛵", "title_ru": "Курьер",                       "title_en": "Courier",                      "sort": 2},
        {"slug": "cargo",            "emoji": "📦", "title_ru": "Грузоперевозки",               "title_en": "Cargo transportation",         "sort": 3},
    ],
    "real-estate": [
        {"slug": "housing-rent",     "emoji": "🏠", "title_ru": "Аренда жилья",                 "title_en": "Housing rental",               "sort": 1},
        {"slug": "housing-buy",      "emoji": "🏡", "title_ru": "Покупка жилья",                "title_en": "Housing purchase",             "sort": 2},
    ],
    "beauty": [
        {"slug": "massage",          "emoji": "💆", "title_ru": "Массаж",                       "title_en": "Massage",                      "sort": 1},
        {"slug": "manicure",         "emoji": "💅", "title_ru": "Маникюр / Педикюр",            "title_en": "Manicure / Pedicure",          "sort": 2},
        {"slug": "cosmetology",      "emoji": "🧖", "title_ru": "Косметолог",                   "title_en": "Cosmetology",                  "sort": 3},
        {"slug": "hairdresser",      "emoji": "💇", "title_ru": "Парикмахер",                   "title_en": "Hairdresser",                  "sort": 4},
        {"slug": "hair-color",       "emoji": "🎨", "title_ru": "Покраска и колорирование",     "title_en": "Hair coloring",                "sort": 5},
        {"slug": "tattoo",           "emoji": "🖊️", "title_ru": "Татуировки",                   "title_en": "Tattoo",                       "sort": 6},
        {"slug": "lashes",           "emoji": "👁️", "title_ru": "Ресницы",                      "title_en": "Lashes",                       "sort": 7},
        {"slug": "brows",            "emoji": "✏️", "title_ru": "Брови",                        "title_en": "Brows",                        "sort": 8},
        {"slug": "makeup",           "emoji": "💄", "title_ru": "Визажист",                     "title_en": "Makeup artist",                "sort": 9},
        {"slug": "barber",           "emoji": "💈", "title_ru": "Барбер",                       "title_en": "Barber",                       "sort": 10},
        {"slug": "epilation",        "emoji": "✨", "title_ru": "Эпиляция",                     "title_en": "Epilation",                    "sort": 11},
    ],
    "doctor": [
        {"slug": "therapist",        "emoji": "🩺", "title_ru": "Терапевт",                     "title_en": "Therapist",                    "sort": 1},
        {"slug": "dentist",          "emoji": "🦷", "title_ru": "Стоматолог",                  "title_en": "Dentist",                      "sort": 2},
        {"slug": "psychologist",     "emoji": "🧠", "title_ru": "Психолог",                    "title_en": "Psychologist",                 "sort": 3},
        {"slug": "dermatologist",    "emoji": "🔬", "title_ru": "Дерматолог",                  "title_en": "Dermatologist",                "sort": 4},
        {"slug": "gynecologist",     "emoji": "👩‍⚕️", "title_ru": "Гинеколог",                   "title_en": "Gynecologist",                 "sort": 5},
        {"slug": "pediatrician",     "emoji": "👶", "title_ru": "Педиатр",                      "title_en": "Pediatrician",                 "sort": 6},
        {"slug": "surgeon",          "emoji": "🏥", "title_ru": "Хирург",                       "title_en": "Surgeon",                      "sort": 7},
        {"slug": "orthopedist",      "emoji": "🦴", "title_ru": "Ортопед",                      "title_en": "Orthopedist",                  "sort": 8},
        {"slug": "neurologist",      "emoji": "🧬", "title_ru": "Невролог",                     "title_en": "Neurologist",                  "sort": 9},
        {"slug": "nutritionist",     "emoji": "🥗", "title_ru": "Нутрициолог",                  "title_en": "Nutritionist",                 "sort": 10},
    ],
    "translator": [
        {"slug": "translator",       "emoji": "🗣️", "title_ru": "Переводчик",                   "title_en": "Translator",                   "sort": 1},
    ],
    "education": [
        {"slug": "language-courses", "emoji": "🌐", "title_ru": "Курсы иностранных языков",     "title_en": "Language courses",             "sort": 1},
        {"slug": "driving-instructor","emoji": "🚗", "title_ru": "Автоинструктор",              "title_en": "Driving instructor",           "sort": 2},
        {"slug": "moto-instructor",  "emoji": "🏍️", "title_ru": "Мотоинструктор",               "title_en": "Moto instructor",              "sort": 3},
        {"slug": "tutor",            "emoji": "📝", "title_ru": "Репетитор",                    "title_en": "Tutor",                        "sort": 4},
    ],
    "home": [
        {"slug": "cleaning",         "emoji": "🧹", "title_ru": "Клининг",                      "title_en": "Cleaning",                     "sort": 1},
        {"slug": "repair",           "emoji": "🔨", "title_ru": "Ремонт и отделка",             "title_en": "Repair & renovation",          "sort": 2},
        {"slug": "plumber",          "emoji": "🔧", "title_ru": "Сантехник",                    "title_en": "Plumber",                      "sort": 3},
        {"slug": "electrician",      "emoji": "⚡", "title_ru": "Электрик",                     "title_en": "Electrician",                  "sort": 4},
        {"slug": "nanny",            "emoji": "👶", "title_ru": "Няни и присмотр",              "title_en": "Nanny & babysitting",          "sort": 5},
        {"slug": "pets",             "emoji": "🐾", "title_ru": "Услуги для животных",          "title_en": "Pet services",                 "sort": 6},
    ],
    "tourism": [
        {"slug": "guide",            "emoji": "🗺️", "title_ru": "Гид",                          "title_en": "Guide",                        "sort": 1},
        {"slug": "excursions",       "emoji": "🏖️", "title_ru": "Экскурсии",                    "title_en": "Excursions",                   "sort": 2},
        {"slug": "visa-support",     "emoji": "🛂", "title_ru": "Визовая поддержка",            "title_en": "Visa support",                 "sort": 3},
        {"slug": "travel-agent",     "emoji": "✈️", "title_ru": "Туристический агент",          "title_en": "Travel agent",                 "sort": 4},
        {"slug": "taxi-transfer",    "emoji": "🚕", "title_ru": "Такси / Трансфер",             "title_en": "Taxi / Transfer",              "sort": 5},
        {"slug": "driver",           "emoji": "🚗", "title_ru": "Водитель с авто",              "title_en": "Driver with car",              "sort": 6},
    ],
    "catering": [
        {"slug": "catering",         "emoji": "🍽️", "title_ru": "Кейтеринг",                    "title_en": "Catering",                     "sort": 1},
        {"slug": "private-chef",     "emoji": "👨‍🍳", "title_ru": "Повар на дом",                "title_en": "Private chef",                 "sort": 2},
        {"slug": "pastry-chef",      "emoji": "🍰", "title_ru": "Кондитер",                     "title_en": "Pastry chef",                  "sort": 3},
        {"slug": "event-management", "emoji": "🎉", "title_ru": "Организация мероприятий",      "title_en": "Event management",             "sort": 4},
        {"slug": "music",            "emoji": "🎵", "title_ru": "Музыкальное сопровождение",    "title_en": "Music accompaniment",          "sort": 5},
    ],
    "fitness": [
        {"slug": "fitness",          "emoji": "💪", "title_ru": "Фитнес",                        "title_en": "Fitness",                      "sort": 1},
        {"slug": "yoga",             "emoji": "🧘", "title_ru": "Йога",                          "title_en": "Yoga",                         "sort": 2},
        {"slug": "martial-arts",     "emoji": "🥋", "title_ru": "Единоборства",                  "title_en": "Martial arts",                 "sort": 3},
        {"slug": "pilates",          "emoji": "🤸", "title_ru": "Пилатес",                       "title_en": "Pilates",                      "sort": 4},
        {"slug": "padel",            "emoji": "🎾", "title_ru": "Падел",                         "title_en": "Padel",                        "sort": 5},
        {"slug": "tennis",           "emoji": "🎾", "title_ru": "Теннис",                        "title_en": "Tennis",                       "sort": 6},
        {"slug": "basketball",       "emoji": "🏀", "title_ru": "Баскетбол",                     "title_en": "Basketball",                   "sort": 7},
        {"slug": "football",         "emoji": "⚽", "title_ru": "Футбол",                        "title_en": "Football",                     "sort": 8},
    ],
    "media-design": [
        {"slug": "photo",            "emoji": "📷", "title_ru": "Фото",                          "title_en": "Photography",                  "sort": 1},
        {"slug": "video",            "emoji": "🎬", "title_ru": "Видео",                         "title_en": "Videography",                  "sort": 2},
        {"slug": "design",           "emoji": "🎨", "title_ru": "Дизайн",                        "title_en": "Design",                       "sort": 3},
        {"slug": "graphics",         "emoji": "🖼️", "title_ru": "Графика",                      "title_en": "Graphics",                     "sort": 4},
    ],
    "legal": [
        {"slug": "notary",           "emoji": "📜", "title_ru": "Нотариус",                      "title_en": "Notary",                       "sort": 1},
        {"slug": "company-registration","emoji": "🏢", "title_ru": "Открытие компании",          "title_en": "Company registration",         "sort": 2},
        {"slug": "lawyer",           "emoji": "⚖️", "title_ru": "Адвокат",                       "title_en": "Lawyer",                       "sort": 3},
        {"slug": "accountant",       "emoji": "📊", "title_ru": "Бухгалтер",                     "title_en": "Accountant",                   "sort": 4},
    ],
    "finance": [
        {"slug": "currency-exchange","emoji": "💱", "title_ru": "Обмен валют",                   "title_en": "Currency exchange",            "sort": 1},
    ],
}


async def seed():
    async with async_session_factory() as session:
        # Clear existing seed data (preserve users/catalog_channels)
        for model in [SegmentKeyword, Segment, Category, City, Country]:
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

        # Categories
        cat_map: dict[str, Category] = {}
        for cat in CATEGORIES:
            obj = Category(
                slug=cat["slug"],
                title_ru=cat["title_ru"],
                title_en=cat["title_en"],
                emoji=cat["emoji"],
                sort_order=cat["sort"],
            )
            session.add(obj)
            cat_map[cat["slug"]] = obj
        await session.flush()

        # Segments (subcategories)
        seg_map: dict[str, Segment] = {}
        for cat_slug, segs in SEGMENTS_BY_CATEGORY.items():
            cat = cat_map.get(cat_slug)
            if not cat:
                continue
            for seg in segs:
                obj = Segment(
                    slug=seg["slug"],
                    title_ru=seg["title_ru"],
                    title_en=seg["title_en"],
                    emoji=seg["emoji"],
                    sort_order=seg["sort"],
                    category_id=cat.id,
                )
                session.add(obj)
                seg_map[seg["slug"]] = obj
        await session.flush()

        # Keywords (from seed_full_keywords.py)
        try:
            from seed.seed_full_keywords import SEGMENT_KEYWORDS
            kw_count = 0
            for seg_slug, kw_data in SEGMENT_KEYWORDS.items():
                seg = seg_map.get(seg_slug)
                if not seg:
                    continue
                for kw_type in ("demand", "stop"):
                    for text in kw_data.get(kw_type, []):
                        session.add(
                            SegmentKeyword(
                                segment_id=seg.id,
                                text=text,
                                keyword_type=kw_type,
                            )
                        )
                        kw_count += 1
            print(f"  Loaded {kw_count} keywords for {len(seg_map)} subcategories")
        except ImportError:
            print("  Keywords file not found — skipping keyword seed")

        await session.commit()
        print("Seed complete!")


if __name__ == "__main__":
    asyncio.run(seed())
