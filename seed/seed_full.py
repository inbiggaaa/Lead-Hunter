"""Full seed: import ALL segment keywords from segment_seed.md."""

import asyncio
import re
from pathlib import Path

from sqlalchemy import select, delete

from app.db.session import async_session_factory
from app.db.models import Segment, SegmentKeyword

SEED_PATH = Path("/app/segment_seed.md")

# Map segment_seed.md slugs to DB segment slugs
SLUG_MAP = {
    "job-hiring": "job-hiring",
    "job-seeking": "job-seeking",
    "bike-rental": "bike-rental",
    "moto-purchase": "moto-purchase",
    "car-rental": "car-rental",
    "real-estate-rent": "real-estate-rent",
    "massage": "massage",
    "cleaning": "cleaning",
    "catering": "catering",
    "beauty": "beauty",  # маникюр, волосы, ресницы, косметология, макияж — все в beauty
    "tattoo": "tattoo",
    "tourism": "tourism",  # гид/экскурсии
    "visa": "visa",
    "translation": "translation",
    "repair": "repair",
    "photo-video": "photo-video",
    "fitness": "fitness",
    "pets": "pets",
    "education": "education",
    "medical": "medical",
    "legal": "legal",
    "it-services": "it-services",
    "design": "design",
    "logistics": "logistics",
    "childcare": "childcare",
    "events": "events",
    "crypto": "crypto",  # обмен валют / крипто
    "other-services": "other-services",
}

# Additional slugs in seed that map to existing segments
EXTRA_SLUGS = {
    "manicure": "beauty",
    "hair": "beauty",
    "lashes-brows": "beauty",
    "cosmetology": "beauty",
    "makeup": "beauty",
    "currency-exchange": "crypto",
    "playstation-rental": "other-services",
    "media-studio": "other-services",
    "guide": "tourism",
    "esoteric": "other-services",
    "food": "catering",
    "yoga": "fitness",
    "driving-lessons": "other-services",
    "translator": "translation",
}

# Segments not in segment_seed.md — manual fallback keywords
FALLBACK_KEYWORDS = {
    "pets": ["ищу ветеринара", "нужен ветеринар", "ищу грумера", "нужен грумер", "передержка собак", "ищу передержку", "нужна передержка", "выгул собак", "ищу выгульщика", "нужна няня для кота", "нужна няня для собаки", "зоотакси", "ищу зоотакси", "looking for vet", "need a vet", "dog walker needed", "pet sitter needed", "pet boarding needed"],
    "logistics": ["ищу доставку", "нужна доставка", "отправить посылку", "ищу курьера", "нужен курьер", "доставка из", "перевозка вещей", "ищу перевозчика", "нужен перевозчик", "нужна доставка груза", "looking for delivery", "need delivery", "courier needed", "shipping needed"],
    "childcare": ["ищу няню", "нужна няня", "ищу бебиситтера", "нужен бебиситтер", "присмотр за ребёнком", "ищу няню на час", "нужна няня на вечер", "ищу няню с опытом", "looking for nanny", "need a babysitter", "childcare needed", "nanny needed"],
    "medical": ["ищу врача", "нужен врач", "ищу стоматолога", "нужен стоматолог", "ищу терапевта", "нужен терапевт", "ищу дерматолога", "нужен дерматолог", "ищу гинеколога", "нужен гинеколог", "нужна консультация врача", "looking for doctor", "need a doctor", "dentist needed", "medical consultation needed"],
    "design": ["ищу дизайнера", "нужен дизайнер", "ищу графического дизайнера", "нужен логотип", "ищу веб-дизайнера", "нужен дизайн", "ищу иллюстратора", "нужен иллюстратор", "looking for designer", "need a designer", "logo design needed", "graphic designer needed", "web designer needed"],
    "repair": ["ищу мастера", "нужен мастер", "нужен ремонт", "ищу сантехника", "нужен сантехник", "ищу электрика", "нужен электрик", "ищу плотника", "нужен плотник", "нужен ремонт техники", "починить", "ищу мастера по ремонту", "нужен ремонт квартиры", "looking for handyman", "need a repair", "plumber needed", "electrician needed", "handyman needed"],
    "real-estate-buy": ["ищу квартиру", "куплю квартиру", "ищу недвижимость", "куплю недвижимость", "ищу дом", "куплю дом", "ищу виллу", "куплю виллу", "ищу апартаменты", "хочу купить квартиру", "хочу купить дом", "покупка недвижимости", "looking to buy", "want to buy property", "buy apartment", "buy house", "buy villa", "property for sale wanted"],
    "it-services": ["ищу программиста", "нужен программист", "ищу разработчика", "нужен разработчик", "ищу веб-разработчика", "нужен сайт", "ищу фрилансера", "нужен фрилансер", "ищу сисадмина", "нужен сисадмин", "нужен бот", "нужен чат-бот", "looking for developer", "need a programmer", "freelancer needed", "web developer needed", "bot development needed"],
    "events": ["ищу ведущего", "нужен ведущий", "ищу организатора", "нужен организатор", "ищу диджея", "нужен диджей", "организация мероприятия", "ищу фотозону", "нужен декор", "нужна организация праздника", "ищу event-менеджера", "looking for event planner", "need a DJ", "event organizer needed", "party planner needed", "wedding planner needed"],
}


async def import_full_keywords():
    if not SEED_PATH.exists():
        print(f"ERROR: {SEED_PATH} not found")
        return

    text = SEED_PATH.read_text(encoding="utf-8")
    lines = text.split("\n")

    # Parse segments: ### 🏷 slug — Title
    segment_pattern = re.compile(r"^###\s+[^\s]+\s+([a-z0-9-]+)\s+—")

    # Parse keywords: demand, stop, synonym blocks
    # Pattern: **Demand:** followed by lines with · separated keywords
    # Lines look like: "keyword1 · keyword2 · keyword3"

    current_slug = None
    current_type = None  # "demand", "stop", "synonym"
    keywords: dict[str, dict[str, list[str]]] = {}  # slug -> {type: [words]}

    for line in lines:
        # Segment header
        sm = segment_pattern.search(line)
        if sm:
            current_slug = sm.group(1)
            if current_slug not in keywords:
                keywords[current_slug] = {"demand": [], "stop": [], "synonym": []}
            current_type = None
            continue

        # Keyword type header: **Demand:** or **Минус-слова:**
        if "**Demand:**" in line or "**demand:**" in line.lower():
            current_type = "demand"
            continue
        if "**Минус-слова" in line or "**stop" in line.lower() or "**Stop:**" in line or "минус-слова" in line.lower():
            current_type = "stop"
            continue
        if "**Короткие anchors" in line or "**Short anchors" in line:
            # Skip short anchors — they're handled by classifier logic
            current_type = None
            continue
        if line.startswith("##") or line.startswith("# "):
            current_slug = None
            current_type = None
            continue

        # Collect keywords
        if current_slug and current_type:
            # Clean markdown formatting
            cleaned = line.strip()
            cleaned = cleaned.replace("·", " · ")  # normalize separators
            # Split on · separator
            parts = [p.strip() for p in cleaned.split("·")]
            for part in parts:
                # Remove bold markers, backticks, etc.
                part = part.strip().strip("*").strip("`").strip()
                if part and len(part) >= 3 and part not in ("Demand", "demand", "Stop", "stop"):
                    keywords[current_slug][current_type].append(part)

    # Import into DB
    async with async_session_factory() as session:
        # Re-open session for imports
        async with async_session_factory() as session2:
            result = await session2.execute(select(Segment))
            seg_map = {s.slug: s.id for s in result.scalars().all()}

            imported = 0
            seen = set()  # (seg_id, text, kw_type) for dedup
            for slug, kw_data in keywords.items():
                db_slug = SLUG_MAP.get(slug) or EXTRA_SLUGS.get(slug)
                if not db_slug:
                    continue

                seg_id = seg_map.get(db_slug)
                if not seg_id:
                    continue

                for kw_type, words in kw_data.items():
                    for word in words:
                        key = (seg_id, word, kw_type)
                        if key in seen:
                            continue
                        seen.add(key)
                        session2.add(SegmentKeyword(
                            segment_id=seg_id,
                            text=word,
                            keyword_type=kw_type,
                        ))
                        imported += 1

            await session2.commit()
            print(f"✅ Imported {imported} keywords across {len(keywords)} segments")

            # Fallback keywords for segments without data in segment_seed.md
            fallback_count = 0
            for slug, words in FALLBACK_KEYWORDS.items():
                seg_id = seg_map.get(slug)
                if not seg_id:
                    continue
                for word in words:
                    key = (seg_id, word, "demand")
                    if key in seen:
                        continue
                    seen.add(key)
                    session2.add(SegmentKeyword(segment_id=seg_id, text=word, keyword_type="demand"))
                    fallback_count += 1

            await session2.commit()
            print(f"✅ Added {fallback_count} fallback keywords")

        # Print stats
        from sqlalchemy import func as sql_func
        result2 = await session2.execute(
            select(Segment.slug, SegmentKeyword.keyword_type, sql_func.count(SegmentKeyword.id))
            .join(SegmentKeyword)
            .group_by(Segment.slug, SegmentKeyword.keyword_type)
        )
        stats = {}
        for slug, ktype, count in result2.all():
            if slug not in stats:
                stats[slug] = {}
            stats[slug][ktype] = count

        for slug, counts in sorted(stats.items()):
            d = counts.get("demand", 0)
            s = counts.get("stop", 0)
            print(f"  {slug}: {d} demand + {s} stop")


if __name__ == "__main__":
    asyncio.run(import_full_keywords())
