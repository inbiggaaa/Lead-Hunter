"""Seed: add synonym keywords for all 29 segments.

Synonyms are treated identically to demand keywords by the classifier.
They cover common variations, English equivalents (expat communities mix RU+EN),
and alternative phrasings that lemma-based matching cannot catch.

Run inside the container:
    python seed/seed_synonyms.py
"""

import asyncio

from sqlalchemy import select

from app.db.session import async_session_factory
from app.db.models import Segment, SegmentKeyword

# ── Synonyms per segment ──
# Each entry: (segment_slug, [synonym_text, ...])
# Key: cover English equivalents + common rephrasings + typos

SYNONYMS = {
    "catering": [  # Кейтеринг / Повара
        "personal chef", "private chef", "home cook",
        "готовка на дому", "домашний повар", "выездной повар",
        "шеф повар на дом", "приготовление еды", "доставка готовой еды",
    ],
    "massage": [  # Массаж
        "massage", "масаж", "массажистка", "масажист",
        "расслабляющий массаж", "лечебный массаж",
    ],
    "bike-rental": [  # Аренда байков
        "rent motorbike", "bike rental", "scooter rental",
        "прокат мото", "прокат байка", "аренда скутера", "прокат скутера",
        "аренда мопеда", "прокат мопеда", "rent scooter", "moto rental",
        "rent a bike", "motorcycle rental",
    ],
    "moto-purchase": [  # Покупка мотоцикла (ищем продавцов)
        "sell motorcycle", "sell motorbike", "sell scooter", "sell bike",
        "продажа мототехники", "продажа байка", "продажа мото", "продажа скутера",
        "продаю мотоцикл недорого", "продаю байк недорого",
        "продаю мотоцикл б/у", "продаю байк б/у",
    ],
    "car-purchase": [  # Покупка авто (ищем продавцов)
        "sell car", "sell vehicle", "sell auto", "sell automobile",
        "продажа авто", "продажа машины", "продажа автомобиля", "автопродажа",
        "продаю авто недорого", "продаю машину недорого",
        "продаю авто б/у", "продаю машину б/у",
        "продажа автомобилей", "продажа машин",
    ],
    "car-rental": [  # Аренда авто
        "rent car", "car rental", "rent a car",
        "прокат авто", "прокат машины", "аренда автомобиля",
        "взять машину напрокат", "взять авто в аренду",
    ],
    "cleaning": [  # Клининг
        "cleaning", "house cleaning", "deep clean",
        "уборщица", "домработница", "химчистка на дому",
        "мойка окон", "генеральная уборка", "клининг дома",
    ],
    "beauty": [  # Красота и уход (уже 313 demand-слов)
        "beauty salon", "hair salon", "nail salon",
        "салон красоты", "парикмахер", "косметолог",
    ],
    "real-estate-rent": [  # Аренда жилья
        "rent apartment", "rent house", "apartment rental",
        "rent condo", "long term rental", "short term rental",
        "снять квартиру", "снять дом", "аренда квартиры",
        "сниму жилье", "ищу квартиру", "посуточная аренда",
    ],
    "real-estate-buy": [  # Покупка жилья
        "buy apartment", "buy condo", "buy house",
        "куплю квартиру", "куплю дом", "покупка жилья",
        "приобрету недвижимость", "ищу квартиру для покупки",
        "buy property", "purchase apartment",
    ],
    "job-hiring": [  # Работа (вакансии)
        "hiring", "job opening", "vacancy",
        "вакансия", "требуется сотрудник", "набор персонала",
        "ищем сотрудника", "ищем работника",
    ],
    "job-seeking": [  # Работа (соискатели)
        "looking for job", "job seeker", "need job",
        "ищу подработку", "нужна работа", "поиск вакансий",
        "хочу работать", "ищу вакансию",
    ],
    "tattoo": [  # Тату
        "tattoo", "tattoo artist", "tattoo master",
        "татуировка", "тату мастер", "набить тату",
        "хочу тату", "сделать тату",
    ],
    "tourism": [  # Туризм / Экскурсии
        "tour guide", "excursion", "tour",
        "экскурсовод", "гид", "поездка",
        "индивидуальный тур", "групповая экскурсия",
    ],
    "visa": [  # Визы и документы
        "visa", "visa run", "border run",
        "визовый центр", "продление визы", "виза ран",
        "документы на визу", "оформление визы",
    ],
    "translation": [  # Переводчики
        "translator", "interpreter",
        "устный перевод", "письменный перевод", "перевод документов",
        "нотариальный перевод",
    ],
    "repair": [  # Ремонт / Мастера
        "handyman", "repair", "fix",
        "мастер на час", "муж на час", "починить",
        "отремонтировать", "сантехник", "электрик",
        "сделать ремонт", "ремонт квартир", "отделка",
    ],
    "photo-video": [  # Фото / Видео
        "photographer", "videographer", "photo shoot",
        "фотограф", "видеограф", "съемка",
        "фотосессия", "видеосъемка", "предметная съемка",
    ],
    "fitness": [  # Фитнес и спорт (уже 182 demand-слова)
        "fitness trainer", "personal trainer", "gym trainer",
        "фитнес тренер", "тренер", "спортзал",
    ],
    "pets": [  # Услуги для животных
        "vet", "veterinarian", "pet sitting", "dog walking",
        "ветеринар", "передержка", "выгул собак",
        "присмотр за животными", "зоогостиница",
    ],
    "education": [  # Обучение / Репетиторы
        "tutor", "teacher", "private tutor",
        "преподаватель", "обучение", "уроки",
        "онлайн занятия", "подготовка к экзаменам",
    ],
    "medical": [  # Медицина / Врачи
        "doctor", "dentist", "clinic",
        "стоматолог", "клиника", "прием врача",
        "медицинская помощь", "запись к врачу",
    ],
    "legal": [  # Юридические услуги
        "lawyer", "attorney", "legal advice",
        "адвокат", "юридическая консультация", "нотариус",
        "помощь юриста",
    ],
    "it-services": [  # IT-услуги
        "developer", "programmer", "web developer",
        "программист", "разработчик", "создание сайтов",
        "it специалист", "компьютерная помощь",
    ],
    "design": [  # Дизайн / Креатив
        "designer", "graphic designer", "web design",
        "веб дизайн", "графический дизайнер", "оформление",
        "создание логотипа", "фирменный стиль",
    ],
    "logistics": [  # Логистика / Доставка
        "delivery", "courier", "shipping",
        "курьер", "доставщик", "перевозка",
        "отправить посылку", "доставка грузов", "карго",
    ],
    "childcare": [  # Няни / Присмотр за детьми
        "babysitter", "nanny", "child care",
        "бебиситтер", "сиделка с ребенком", "присмотр за ребенком",
        "детский сад на дому", "нянечка",
    ],
    "events": [  # Организация мероприятий
        "event planner", "event organizer", "party planner",
        "организатор мероприятий", "ведущий", "тамада",
        "организация праздников", "event management",
    ],
    "crypto": [  # Обмен валют
        "exchange", "currency exchange", "money exchange",
        "обменник", "обменять доллары", "обменять рубли",
        "поменять валюту", "криптообмен", "p2p обмен",
    ],
    "driving-lessons": [  # Обучение вождению
        "driving school", "driving instructor", "learn driving",
        "инструктор по вождению", "учиться водить", "категория A",
        "права на байк", "права на мотоцикл", "получить права",
        "driving license", "motorbike license",
    ],
}


async def seed_synonyms():
    """Insert synonym keywords into the database."""
    async with async_session_factory() as session:
        # Load segment slugs → IDs
        segments_result = await session.execute(select(Segment))
        segments = {s.slug: s.id for s in segments_result.scalars().all()}

        total_added = 0
        total_skipped = 0

        for slug, synonyms in SYNONYMS.items():
            if slug not in segments:
                print(f"  ⚠️  Unknown segment: {slug}")
                continue

            seg_id = segments[slug]

            for text in synonyms:
                # Check if this synonym already exists for this segment
                existing = await session.execute(
                    select(SegmentKeyword).where(
                        SegmentKeyword.segment_id == seg_id,
                        SegmentKeyword.text == text,
                    )
                )
                if existing.scalar_one_or_none():
                    total_skipped += 1
                    continue

                session.add(SegmentKeyword(
                    segment_id=seg_id,
                    text=text,
                    keyword_type="synonym",
                    is_active=True,
                ))
                total_added += 1

        await session.commit()

    print(f"✅ Synonyms seeded: {total_added} added, {total_skipped} skipped (already exist)")


if __name__ == "__main__":
    asyncio.run(seed_synonyms())
